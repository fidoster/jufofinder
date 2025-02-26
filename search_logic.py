from api_utils import get_jufo_level, crossref_search  # Added crossref_search
import time
import logging
import json  # Added for json.dumps

from database import get_cached_results, cache_results, save_search  # Added database imports

logger = logging.getLogger(__name__)

stop_search = False
jufo_cache = {}

def sort_results(results):
    def sort_key(item):
        level = item["level"]
        return (-1 if level == "Not JUFO Ranked" else level, item["title"])
    return sorted(results, key=sort_key, reverse=True)

def search_stream(keywords, max_articles_per_keyword=1000, target_jufo=None, year_range=None):
    global stop_search
    stop_search = False
    total_articles = max_articles_per_keyword * len(keywords.split(",")) if not target_jufo else 1000
    articles_processed = 0
    jufo_2_3_count = 0
    results = []
    cached_articles = set()

    min_year = None
    max_year = None
    if year_range and year_range != "all":
        if "-" in year_range:
            min_year, max_year = map(int, year_range.split("-"))
        else:
            min_year = int(year_range)
            max_year = 9999

    for keyword in keywords.split(","):
        cached = get_cached_results(keyword.strip())
        for article in cached:
            if article["link"] not in cached_articles and len([r for r in results if r["raw_info"].startswith(keyword.strip())]) < max_articles_per_keyword:
                year = int(article["year"]) if article["year"] not in ("N/A", "None") and article["year"] else None
                if year_range == "all" or (year and (not min_year or year >= min_year) and (not max_year or year <= max_year)):
                    logger.debug(f"Cached article: {article['title']}, Year: {article['year']}")
                    results.append(article)
                    cached_articles.add(article["link"])
                    if article["level"] in [2, 3]:
                        jufo_2_3_count += 1

    should_stop = False
    for keyword in keywords.split(","):
        keyword = keyword.strip()
        keyword_results = [r for r in results if r["raw_info"].startswith(keyword)]
        offset = len(keyword_results)
        keyword_articles = offset

        while articles_processed < total_articles and not stop_search and not should_stop:
            articles = crossref_search(keyword, rows=20, offset=offset)
            if not articles:
                logger.warning(f"No more articles from Crossref for {keyword} at offset {offset}")
                break
            for article in articles:
                if article["link"] not in cached_articles:
                    year = int(article["year"]) if article["year"] not in ("N/A", "None") and article["year"] else None
                    if year_range == "all" or (year and (not min_year or year >= min_year) and (not max_year or year <= max_year)):
                        articles_processed += 1
                        keyword_articles += 1
                        logger.info(f"Processing article {articles_processed}/{total_articles}: {article['title']}, Year: {article['year']}")
                        yield f"data: {json.dumps({'status': 'Checking', 'article': article['title'], 'progress': min((articles_processed / total_articles) * 100, 100), 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count, 'results': results})}\n\n"
                        level = get_jufo_level(article["journal"], jufo_cache)
                        article["level"] = level if level else "Not JUFO Ranked"
                        results.append(article)
                        cached_articles.add(article["link"])
                        if level in [2, 3]:
                            jufo_2_3_count += 1
                            logger.info(f"Found JUFO 2/3 article: {article['title']}, Level: {level}")
                        if target_jufo and jufo_2_3_count >= target_jufo:
                            should_stop = True
                            logger.info(f"Target JUFO 2/3 ({target_jufo}) reached at {jufo_2_3_count}")
                            break
                time.sleep(1)
            if should_stop:
                break
            offset += 20
            time.sleep(1)

    sorted_results = sort_results(results)
    cache_results(keywords, sorted_results)
    save_search(keywords, sorted_results)
    status = "Stopped" if stop_search or should_stop else "Complete"
    logger.info(f"Search {status}: Processed {articles_processed}/{total_articles}, JUFO 2/3: {jufo_2_3_count}")
    yield f"data: {json.dumps({'status': status, 'results': sorted_results, 'progress': 100, 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"