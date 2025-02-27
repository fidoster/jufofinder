from api_utils import get_jufo_level, crossref_search
import time
import logging
import json
from database import get_cached_results, cache_results, save_search

logger = logging.getLogger(__name__)

# Global variables used to control the search
stop_search = False
jufo_cache = {}

def sort_results(results):
    def sort_key(item):
        level = item["level"]
        return (-1 if level == "Not JUFO Ranked" else level, item["title"])
    return sorted(results, key=sort_key, reverse=True)

def search_stream(keywords, max_articles_per_keyword=1000, target_jufo=None, year_range=None):
    global stop_search
    stop_search = False  # Reset stop flag for new search
    total_articles = max_articles_per_keyword * len(keywords.split(",")) if not target_jufo else 1000
    articles_processed = 0
    jufo_2_3_count = 0
    results = []
    cached_articles = set()
    no_new_articles_count = 0

    min_year = None
    max_year = None
    if year_range and year_range != "all":
        if "-" in year_range:
            min_year, max_year = map(int, year_range.split("-"))
            if min_year > max_year:
                logger.warning(f"Invalid year range {year_range}, defaulting to all years")
                min_year, max_year = None, None
        else:
            min_year = int(year_range)
            max_year = 9999

    # Process cached results
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
            if stop_search:
                logger.info("Stopping search requested, initiating save")
                yield f"data: {json.dumps({'status': 'Stopping', 'message': 'Saving results...'})}\n\n"
                sorted_results = sort_results(results)
                cache_results(keywords, sorted_results)
                start_time = time.time()
                save_search(keywords, sorted_results)
                elapsed_time = time.time() - start_time
                sleep_time = max(0.5, elapsed_time * 2)  # Dynamic sleep based on save duration
                time.sleep(sleep_time)  # Ensure save completes
                yield f"data: {json.dumps({'status': 'Stopped', 'results': sorted_results, 'progress': min((articles_processed / total_articles) * 100, 100), 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"
                return

            articles = crossref_search(keyword, rows=20, offset=offset)
            if not articles:
                logger.warning(f"No more articles from Crossref for {keyword} at offset {offset}")
                no_new_articles_count += 1
                if min_year and no_new_articles_count >= 3:
                    logger.info(f"No articles found in custom range {year_range}, stopping search")
                    should_stop = True
                break

            no_new_articles_count = 0
            for article in articles:
                if stop_search:
                    logger.info("Stopping search mid-article, initiating save")
                    yield f"data: {json.dumps({'status': 'Stopping', 'message': 'Saving results...'})}\n\n"
                    sorted_results = sort_results(results)
                    cache_results(keywords, sorted_results)
                    start_time = time.time()
                    save_search(keywords, sorted_results)
                    elapsed_time = time.time() - start_time
                    sleep_time = max(0.5, elapsed_time * 2)
                    time.sleep(sleep_time)
                    yield f"data: {json.dumps({'status': 'Stopped', 'results': sorted_results, 'progress': min((articles_processed / total_articles) * 100, 100), 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"
                    return

                if article["link"] not in cached_articles:
                    year = int(article["year"]) if article["year"] not in ("N/A", "None") and article["year"] else None
                    if year_range == "all" or (year and (not min_year or year >= min_year) and (not max_year or year <= max_year)):
                        articles_processed += 1
                        logger.debug(f"Processing article {articles_processed}: {article['title']}")
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
                if stop_search:  # Additional check
                    logger.info("Additional stop check triggered")
                    yield f"data: {json.dumps({'status': 'Stopping', 'message': 'Saving results...'})}\n\n"
                    sorted_results = sort_results(results)
                    cache_results(keywords, sorted_results)
                    start_time = time.time()
                    save_search(keywords, sorted_results)
                    elapsed_time = time.time() - start_time
                    sleep_time = max(0.5, elapsed_time * 2)
                    time.sleep(sleep_time)
                    yield f"data: {json.dumps({'status': 'Stopped', 'results': sorted_results, 'progress': min((articles_processed / total_articles) * 100, 100), 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"
                    return
            if should_stop or stop_search:
                break
            offset += 20
            time.sleep(0.1)

        if should_stop or stop_search:
            break

    sorted_results = sort_results(results)
    cache_results(keywords, sorted_results)
    save_search(keywords, sorted_results)
    status = "Stopped" if stop_search or should_stop else "Complete"
    logger.info(f"Search {status}: Processed {articles_processed}/{total_articles}, JUFO 2/3: {jufo_2_3_count}")
    yield f"data: {json.dumps({'status': status, 'results': sorted_results, 'progress': 100, 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"
