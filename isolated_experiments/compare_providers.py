import time
import json
import sys
from typing import Dict, Any, List
from isolated_experiments.ddg_html_provider import DDGHtmlSearchProvider
from isolated_experiments.bing_web_provider import BingWebSearchProvider
from prospector.search_engine import SearchEngine

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def benchmark_query(query: str, max_results: int = 5) -> Dict[str, Any]:
    ddg_html = DDGHtmlSearchProvider()
    bing_web = BingWebSearchProvider()
    original_se = SearchEngine()

    report = {"query": query, "providers": {}}

    # 1. Test Workaround 2A (DDG HTML Lite)
    t0 = time.time()
    try:
        res_2a = ddg_html.query(query, max_results=max_results)
        t_2a = round(time.time() - t0, 3)
        status_2a = "SUCCESS"
    except Exception as e:
        res_2a = []
        t_2a = round(time.time() - t0, 3)
        status_2a = f"ERROR: {e}"

    report["providers"]["2A_DDG_HTML"] = {
        "status": status_2a,
        "latency_sec": t_2a,
        "count": len(res_2a),
        "results": res_2a,
    }

    # 2. Test Workaround 2B (Bing Web)
    t0 = time.time()
    try:
        res_2b = bing_web.query(query, max_results=max_results)
        t_2b = round(time.time() - t0, 3)
        status_2b = "SUCCESS"
    except Exception as e:
        res_2b = []
        t_2b = round(time.time() - t0, 3)
        status_2b = f"ERROR: {e}"

    report["providers"]["2B_Bing_Web"] = {
        "status": status_2b,
        "latency_sec": t_2b,
        "count": len(res_2b),
        "results": res_2b,
    }

    # 3. Test Original Code (SearchEngine / Yahoo-DDG API)
    t0 = time.time()
    try:
        res_orig = original_se.query(query, max_results=max_results)
        t_orig = round(time.time() - t0, 3)
        status_orig = "SUCCESS"
    except Exception as e:
        res_orig = []
        t_orig = round(time.time() - t0, 3)
        status_orig = f"ERROR: {e}"

    report["providers"]["Original_Engine"] = {
        "status": status_orig,
        "latency_sec": t_orig,
        "count": len(res_orig),
        "results": res_orig,
    }

    return report


if __name__ == "__main__":
    test_queries = [
        "site:linkedin.com/in Kisah HR",
        "site:linkedin.com/in thebigcjobs Founder",
        "site:linkedin.com/in Spectro Cloud CEO",
    ]

    all_reports = []
    print("=" * 70)
    print("RUNNING LIVE HEAD-TO-HEAD COMPARISON BENCHMARK")
    print("=" * 70)

    for q in test_queries:
        print(f"\n--> Benchmarking Query: {q}")
        rep = benchmark_query(q, max_results=5)
        all_reports.append(rep)

        for prov, data in rep["providers"].items():
            print(f"  [{prov}] Status: {data['status']} | Count: {data['count']} | Time: {data['latency_sec']}s")
            for idx, r in enumerate(data["results"][:2], 1):
                print(f"      {idx}. {r.get('title')[:60]} -> {r.get('link')}")

    with open("isolated_experiments/comparison_report.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)

    print("\n[+] Full detailed JSON report saved to isolated_experiments/comparison_report.json")
