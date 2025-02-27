from flask import Blueprint, render_template, request, Response, jsonify, send_file
import json
import logging
import pandas as pd
from search_logic import search_stream, sort_results  # Removed stop_search from here.
import search_logic  # Import the module to update its global variable.
from database import save_search, get_history, delete_search, get_cached_results, cache_results
import sqlite3

bp = Blueprint('routes', __name__)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@bp.route("/")
def index():
    return render_template("index.html")

@bp.route("/search_stream")
def search_stream_route():
    keywords = request.args.get("keywords")
    max_articles = int(request.args.get("max_articles", 1000))
    target_jufo = int(request.args.get("target_jufo", 0)) if request.args.get("target_jufo") else None
    year_range = request.args.get("year_range", "all")
    logger.info(f"Starting search: keywords={keywords}, max_articles={max_articles}, target_jufo={target_jufo}, year_range={year_range}")
    return Response(search_stream(keywords, max_articles, target_jufo, year_range), mimetype="text/event-stream")

@bp.route("/stop_search", methods=["POST"])
def stop_search_route():
    keywords = request.args.get("keywords", "default")
    if not keywords:
        keywords = request.form.get("keywords", "default")  # Fallback
    # Update the stop flag in the search_logic module directly.
    search_logic.stop_search = True
    logger.info(f"Stop search requested for keywords: {keywords}")
    return jsonify({"status": "stopped"})

@bp.route("/history")
def history():
    searches = get_history()
    return render_template("history.html", searches=searches)

@bp.route("/history_results/<path:keywords>")
def history_results(keywords):
    searches = get_history()
    for search in searches:
        if search["keywords"] == keywords:
            results = eval(search["results"])
            sorted_results = sort_results(results)
            return render_template("index.html", results=sorted_results, from_history=True, keywords=keywords)
    return "Search not found", 404

@bp.route("/delete_search/<path:keywords>", methods=["POST"])
def delete_search_route(keywords):
    delete_search(keywords)
    return jsonify({"status": "success"})

@bp.route("/delete_article/<path:keywords>/<path:link>", methods=["POST"])
def delete_article(keywords, link):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("SELECT results FROM searches WHERE keywords = ?", (keywords,))
    result = c.fetchone()
    if result:
        results = eval(result[0])
        updated_results = [r for r in results if r["link"] != link]
        if len(updated_results) < len(results):
            c.execute("UPDATE searches SET results = ?, count = ? WHERE keywords = ?", 
                      (str(updated_results), len(updated_results), keywords))
            conn.commit()
            conn.close()
            logger.info(f"Article deleted from {keywords}, remaining count: {len(updated_results)}")
            return jsonify({"status": "success", "remaining_count": len(updated_results)})
    conn.close()
    logger.warning(f"Article not found for deletion: {link}")
    return jsonify({"status": "not_found"}), 404

@bp.route("/delete_not_jufo/<path:keywords>", methods=["POST"])
def delete_not_jufo(keywords):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("SELECT results FROM searches WHERE keywords = ?", (keywords,))
    result = c.fetchone()
    if result:
        results = eval(result[0])
        updated_results = [r for r in results if r["level"] != "Not JUFO Ranked"]
        if len(updated_results) < len(results):
            c.execute("UPDATE searches SET results = ?, count = ? WHERE keywords = ?", 
                      (str(updated_results), len(updated_results), keywords))
            conn.commit()
            conn.close()
            logger.info(f"Non-JUFO articles deleted from {keywords}, remaining count: {len(updated_results)}")
            return jsonify({"status": "success", "remaining_count": len(updated_results)})
    conn.close()
    logger.warning(f"No non-JUFO articles found to delete for: {keywords}")
    return jsonify({"status": "not_found"}), 404

@bp.route("/download")
def download_csv():
    keywords = request.args.get("keywords", "latest_search")
    results = [r for s in get_history() if s["keywords"] == keywords for r in eval(s["results"])]
    df = pd.DataFrame(results)
    df.to_csv("results.csv", index=False)
    return send_file("results.csv", as_attachment=True, download_name=f"{keywords}_results.csv")
