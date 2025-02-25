from flask import Flask, render_template, request, Response, jsonify, send_file
import requests
import pandas as pd
import time
import random
from fuzzywuzzy import fuzz
from database import init_db, save_search, get_history, delete_search, get_cached_results, cache_results
import json

app = Flask(__name__)

# Global flag for stopping the search
stop_search = False

# Cache for JUFO levels to avoid repeated API calls
jufo_cache = {}

# Crossref API setup
base_url = "https://api.crossref.org/works"

def crossref_search(query, rows=20, offset=0):
    params = {"query": query, "rows": rows, "offset": offset, "select": "DOI,title,container-title,issued"}
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"Crossref request failed: {response.status_code} - {response.text}")
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

# JUFO API functions
def fetch_jufo_api(url):
    try:
        response = requests.get(url, timeout=10)
        return response.json() if response.ok and isinstance(response.json(), list) and response.json() else None
    except:
        return None

def try_jufo_queries_in_sequence(query):
    base_url = "https://jufo-rest.csc.fi/v1.1/etsi.php"
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
        return jufo_cache[journal_name]
    results = try_jufo_queries_in_sequence(journal_name)
    if not results:
        jufo_cache[journal_name] = None
        return None
    best_match = max(results, key=lambda x: fuzz.ratio(x.get("Name", ""), journal_name), default=None)
    if best_match and fuzz.ratio(best_match.get("Name", ""), journal_name) > 70:
        level = augment_jufo_result(best_match)
        jufo_cache[journal_name] = level
        return level
    jufo_cache[journal_name] = None
    return None

# Sort results by JUFO level (descending)
def sort_results(results):
    def sort_key(item):
        level = item["level"]
        return (-1 if level == "Not JUFO Ranked" else level, item["title"])
    return sorted(results, key=sort_key, reverse=True)

# Generator for search progress
def search_stream(keywords, max_articles_per_keyword=100, target_jufo=None, year_range=None):
    global stop_search
    stop_search = False
    total_articles = max_articles_per_keyword * len(keywords.split(",")) if not target_jufo else 1000
    articles_processed = 0
    jufo_2_3_count = 0
    results = []
    cached_articles = set()

    # Parse year range
    min_year = None
    max_year = None
    if year_range and year_range != "all":
        if "-" in year_range:
            min_year, max_year = map(int, year_range.split("-"))
        else:
            min_year = int(year_range)
            max_year = 9999

    # Load cached results
    for keyword in keywords.split(","):
        cached = get_cached_results(keyword.strip())
        for article in cached:
            if article["link"] not in cached_articles and len([r for r in results if r["raw_info"].startswith(keyword.strip())]) < max_articles_per_keyword:
                year = int(article["year"]) if article["year"] not in ("N/A", "None") and article["year"] else None
                if year_range == "all" or (year and (not min_year or year >= min_year) and (not max_year or year <= max_year)):
                    print(f"Cached article: {article['title']}, Year: {article['year']}")  # Debug
                    results.append(article)
                    cached_articles.add(article["link"])
                    if article["level"] in [2, 3]:
                        jufo_2_3_count += 1

    for keyword in keywords.split(","):
        keyword = keyword.strip()
        keyword_results = [r for r in results if r["raw_info"].startswith(keyword)]
        offset = len(keyword_results)
        keyword_articles = offset

        while (keyword_articles < max_articles_per_keyword or (target_jufo and jufo_2_3_count < target_jufo)) and articles_processed < total_articles and not stop_search:
            articles = crossref_search(keyword, rows=20, offset=offset)
            if not articles:
                break
            for article in articles:
                if article["link"] not in cached_articles and keyword_articles < max_articles_per_keyword:
                    year = int(article["year"]) if article["year"] not in ("N/A", "None") and article["year"] else None
                    if year_range == "all" or (year and (not min_year or year >= min_year) and (not max_year or year <= max_year)):
                        articles_processed += 1
                        keyword_articles += 1
                        print(f"New article: {article['title']}, Year: {article['year']}")  # Debug
                        yield f"data: {json.dumps({'status': 'Checking', 'article': article['title'], 'progress': min((articles_processed / total_articles) * 100, 100), 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count, 'results': results})}\n\n"
                        level = get_jufo_level(article["journal"])
                        article["level"] = level if level else "Not JUFO Ranked"
                        results.append(article)
                        cached_articles.add(article["link"])
                        if level in [2, 3]:
                            jufo_2_3_count += 1
                        if target_jufo and jufo_2_3_count >= target_jufo:
                            break
                time.sleep(random.uniform(0.1, 0.5))  # Reduced sleep
            if target_jufo and jufo_2_3_count >= target_jufo:
                break
            offset += 20
            time.sleep(random.uniform(0.5, 1))  # Reduced sleep
    
    sorted_results = sort_results(results)
    cache_results(keywords, sorted_results)
    save_search(keywords, sorted_results)
    status = "Stopped" if stop_search else "Complete"
    yield f"data: {json.dumps({'status': status, 'results': sorted_results, 'progress': 100, 'current': articles_processed, 'total': total_articles, 'jufo_count': jufo_2_3_count})}\n\n"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search_stream")
def search_stream_route():
    keywords = request.args.get("keywords")
    max_articles = int(request.args.get("max_articles", 100))
    target_jufo = int(request.args.get("target_jufo", 0)) if request.args.get("target_jufo") else None
    year_range = request.args.get("year_range", "all")
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