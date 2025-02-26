import requests
import logging
from fuzzywuzzy import fuzz  # Added for fuzz.ratio

logger = logging.getLogger(__name__)

def crossref_search(query, rows=20, offset=0):
    base_url = "https://api.crossref.org/works"
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

def get_jufo_level(journal_name, jufo_cache=None):
    if journal_name == "Unknown":
        return None
    if jufo_cache is None:
        jufo_cache = {}
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