from flask import Flask, render_template, request, Response, jsonify, send_file
import requests
import pandas as pd
import time
import random
from fuzzywuzzy import fuzz
from database import init_db, save_search, get_history, delete_search, get_cached_results, cache_results
import json
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global flag for stopping the search
stop_search = False

# Cache for JUFO levels
jufo_cache = {}

# Crossref API setup
base_url = "https://api.crossref.org/works"

def crossref_search(query, rows=20, offset=0):
    params = {"query": query, "rows": rows, "offset": offset, "select": "DOI,title,container-title,issued"}
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        logger.error(f"Crossref request failed: {response.status_code} - {response.text}")
        return []
    data = response.json()
    items = data["message"]["items"]
    return [{
        "title": item.get("title", ["No title"])[0],
        "link": f"https://doi.org/{item['DOI']}" if "DOI" in item else "No link available",
        "journal": item.get("container-title", ["Unknown"])[0],
        "year": str(item.get("issued", {}).get("date-parts", [[""]])[0][0]) if item.get("issued", {}).get("date-parts", [[""]])[0][0] else "N/A",
        "raw_info": f"{', '.join(item.get('author', [{'given': '', 'family': ''}])[0].values())} - {item.get('container-title', [''])[0]}, {item.get('issued', {}).get('date-parts', [['']])[0][0]}"
    } for item in items] if items else []

def fetch_jufo_api(url):
    try:
        response = requests.get(url, timeout=10)
        if response.ok and isinstance(response.json(), list) and response.json():
            return response.json()
        logger.warning(f"JUFO API returned non-list or empty: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        logger.error(f"JUFO API error: {str(e)}")
        return None

def try_jufo_queries_in_sequence(query):
    base_url = "https://jufo-rest.csc.fi/v1.1/etsi.php"
    # Truncate long queries to avoid 400 errors
    query = query[:100] if len(query) > 100 else query
    for param in ["nimi", "nimi", "issn"]:
        url = f"{base_url}?{param}={requests.utils.quote(query if param != 'nimi' or param == 'nimi' and query == query else f'*{query}*')}"
        data = fetch_jufo_api(url)
        if data:
            return data
    return None

def augment_jufo_result(item):
    if not item.get("Jufo_ID"):
        return None
    details_url = f"https://jufo-rest.csc.fi/v1.1/kanava/{item['Jufo_ID']}"
    response = requests.get(details_url, timeout=10)
    if response.ok:
        detail_json = response.json()
        if detail_json and len(detail_json) > 0:
            raw_level = detail_json[0].get("Level", "")
            return int(raw_level) if raw_level.isdigit() else None
    return None

def get_jufo_level(journal_name):
    if journal_name == "Unknown":
        return None
    if journal_name in jufo_cache:
        logger.debug(f"JUFO cache hit: {journal_name} -> {jufo_cache[journal_name]}")
        return jufo_cache[journal_name]
    results = try_jufo_queries_in_sequence(journal_name)
    if not results:
        logger.debug(f"No JUFO results for: {journal_name}")
        jufo_cache[journal_name] = None
        return None
    best_match = max(results, key=lambda x: fuzz.ratio(x.get("Name", ""), journal_name), default=None)
    ratio = fuzz.ratio(best_match.get("Name", ""), journal_name) if best_match else 0
    logger.debug(f"JUFO match for {journal_name}: {best_match.get('Name', '') if best_match else 'None'}, Ratio: {ratio}")
    if best_match and ratio > 60:
        level = augment_jufo_result(best_match)
        jufo_cache[journal_name] = level
        logger.debug(f"JUFO level assigned: {journal_name} -> {level}")
        return level
    jufo_cache[journal_name] = None
    with open("unmatched_journals.txt", "a") as f:
        f.write(f"{journal_name}, Ratio: {ratio}\n")
    return None

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
                        level = get_jufo_level(article["journal"])
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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search_stream")
def search_stream_route():
    keywords = request.args.get("keywords")
    max_articles = int(request.args.get("max_articles", 1000))  # Default to 1000
    target_jufo = int(request.args.get("target_jufo", 0)) if request.args.get("target_jufo") else None
    year_range = request.args.get("year_range", "all")
    logger.info(f"Starting search: keywords={keywords}, max_articles={max_articles}, target_jufo={target_jufo}, year_range={year_range}")
    return Response(search_stream(keywords, max_articles, target_jufo, year_range), mimetype="text/event-stream")

@app.route("/stop_search", methods=["POST"])
def stop_search_route():
    global stop_search
    stop_search = True
    return jsonify({"status": "stopped"})

@app.route("/history")
def history():
    searches = get_history()
    return render_template("history.html", searches=searches)

@app.route("/history_results/<path:keywords>")
def history_results(keywords):
    searches = get_history()
    for search in searches:
        if search["keywords"] == keywords:
            results = eval(search["results"])
            sorted_results = sort_results(results)
            return render_template("index.html", results=sorted_results, from_history=True, keywords=keywords)
    return "Search not found", 404

@app.route("/delete_search/<path:keywords>")
def delete_search_route(keywords):
    delete_search(keywords)
    return jsonify({"status": "success"})

@app.route("/download")
def download_csv():
    keywords = request.args.get("keywords", "latest_search")
    results = [r for s in get_history() if s["keywords"] == keywords for r in eval(s["results"])]
    df = pd.DataFrame(results)
    df.to_csv("results.csv", index=False)
    return send_file("results.csv", as_attachment=True, download_name=f"{keywords}_results.csv")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)