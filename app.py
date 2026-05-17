
"""
Energy Infrastructure Target Finder

Streamlit app for TimeX-style energy/infrastructure origination.

Features:
- Limited filters: vertical, geography, target angle.
- Company/project discovery through public-source search queries.
- Optional live search with SERPAPI_KEY or BRAVE_API_KEY.
- Target scoring and banking-angle classification.
- Public LinkedIn profile search-query generation.
- Optional people-search pass using search API.
- Apollo API key placeholder for later contact enrichment.
- CSV export.
- "Send to TimeX Gmail" mailto button.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Streamlit Cloud:
    Main file path: app.py
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import pandas as pd
import requests
import streamlit as st


# ----------------------------
# Configuration
# ----------------------------

VERTICALS = [
    "Renewables / Solar / Wind",
    "Battery Storage",
    "Grid / Transmission",
    "Utility Services",
    "Water / Environmental Infrastructure",
    "Oil & Gas / Pipeline Services",
    "Industrial Infrastructure",
]

GEOGRAPHY_DEFAULT = "Minnesota Iowa Wisconsin North Dakota South Dakota"

ANGLES = [
    "Hidden developers / project sponsors",
    "Capital raise candidates",
    "M&A / consolidation targets",
    "Contractors with backlog",
    "Refinancing / special situations",
]

PUBLIC_SOURCES = [
    ("FERC eLibrary", "https://elibrary.ferc.gov/"),
    ("MISO Generator Interconnection Queue", "https://www.misoenergy.org/planning/resource-utilization/GI_Queue/"),
    ("MISO Active Project Map", "https://giqueue.misoenergy.org/PublicGiQueueMap/index.html"),
    ("Interconnection.fyi", "https://www.interconnection.fyi/"),
    ("Berkeley Lab Queue Maps", "https://emp.lbl.gov/maps-projects-region-state-and-county"),
    ("EIA Electricity Data", "https://www.eia.gov/electricity/data.php"),
    ("EPA ECHO", "https://echo.epa.gov/"),
    ("SAM.gov", "https://sam.gov/"),
    ("OpenCorporates", "https://opencorporates.com/"),
]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str


@dataclass
class Target:
    priority_score: int
    confidence: str
    company: str
    evidence: str
    likely_angle: str
    best_roles: str
    source_url: str
    source_snippet: str
    missing_data: str
    next_step: str
    linkedin_queries: str
    thesis: str


@dataclass
class PersonCandidate:
    fit_score: int
    company: str
    person_or_profile: str
    title_guess: str
    linkedin_url: str
    source_title: str
    source_snippet: str
    query: str


# ----------------------------
# Helpers
# ----------------------------

def get_secret(name: str) -> str:
    """Read from Streamlit secrets first, then environment variables."""
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, "").strip()


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def linked_button_url(query: str) -> str:
    return google_search_url(query)


def email_target_list_link(df: pd.DataFrame, to_email: str = "tyler.a.brickle@gmail.com") -> str:
    subject = "TimeX Energy Infrastructure Target List"
    lines = []
    for _, row in df.head(15).iterrows():
        lines.append(
            f"""Company: {row.get('company', '')}
Priority: {row.get('priority_score', '')}
Confidence: {row.get('confidence', '')}
Likely Angle: {row.get('likely_angle', '')}
Evidence: {row.get('evidence', '')}
Best Roles: {row.get('best_roles', '')}
Source: {row.get('source_url', '')}
Next Step: {row.get('next_step', '')}
"""
        )
    body = "\n---\n".join(lines)
    return (
        f"mailto:{to_email}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body[:7000])}"
    )


# ----------------------------
# Query generation
# ----------------------------

def terms_for(vertical: str) -> Dict[str, str]:
    mapping = {
        "Renewables / Solar / Wind": {
            "company": "renewable energy developer",
            "project": "solar OR wind project",
            "asset": "solar wind renewable energy project",
        },
        "Battery Storage": {
            "company": "battery storage developer",
            "project": "battery energy storage project",
            "asset": "BESS battery storage project",
        },
        "Grid / Transmission": {
            "company": "transmission grid services",
            "project": "transmission line OR substation project",
            "asset": "transmission substation grid project",
        },
        "Utility Services": {
            "company": "utility services contractor",
            "project": "utility construction project",
            "asset": "utility infrastructure contract",
        },
        "Water / Environmental Infrastructure": {
            "company": "water environmental infrastructure",
            "project": "water wastewater infrastructure project",
            "asset": "wastewater water infrastructure project",
        },
        "Oil & Gas / Pipeline Services": {
            "company": "pipeline oil gas services",
            "project": "pipeline project",
            "asset": "pipeline oil gas infrastructure project",
        },
        "Industrial Infrastructure": {
            "company": "industrial infrastructure services",
            "project": "industrial facility expansion",
            "asset": "industrial infrastructure facility expansion",
        },
    }
    return mapping.get(vertical, {"company": vertical, "project": vertical, "asset": vertical})


def generate_company_queries(vertical: str, geography: str, angle: str) -> List[str]:
    t = terms_for(vertical)

    if "Hidden developers" in angle:
        return [
            f'"{t["project"]}" "{geography}" "interconnection queue" developer',
            f'"{t["project"]}" "{geography}" "conditional use permit" applicant',
            f'"{t["project"]}" "{geography}" "planning commission" "public hearing"',
            f'"{t["project"]}" "{geography}" "project LLC" OR "Holdings LLC"',
            f'"{t["project"]}" "{geography}" "registered agent" developer',
            f'"{t["asset"]}" "{geography}" "site permit" "developer"',
        ]

    if "Capital raise" in angle:
        return [
            f'"{t["company"]}" "{geography}" "expansion" OR "new facility"',
            f'"{t["company"]}" "{geography}" "contract awarded" OR backlog',
            f'"{t["company"]}" "{geography}" "project finance" OR "construction financing"',
            f'"{t["company"]}" "{geography}" "fleet expansion" OR "equipment financing"',
            f'"{t["company"]}" "{geography}" "CFO" "appointed" OR "joins as CFO"',
            f'"{t["company"]}" "{geography}" "growth capital"',
        ]

    if "M&A" in angle:
        return [
            f'"{t["company"]}" "{geography}" acquired OR acquisition OR recapitalization',
            f'"{t["company"]}" "{geography}" "private equity" "portfolio company"',
            f'"{t["company"]}" "{geography}" "family owned" OR "founder owned"',
            f'"{t["company"]}" "{geography}" "platform investment"',
            f'"{t["company"]}" "{geography}" "strategic investment"',
            f'"{t["company"]}" "{geography}" "recapitalized by"',
        ]

    if "Contractors" in angle:
        return [
            f'"{t["company"]}" "{geography}" "awarded contract"',
            f'"{t["company"]}" "{geography}" "bid tabulation"',
            f'"{t["company"]}" "{geography}" "municipal contract"',
            f'"{t["company"]}" "{geography}" "request for proposals"',
            f'"{t["company"]}" "{geography}" "notice to proceed"',
            f'"{t["company"]}" "{geography}" "contract award"',
        ]

    return [
        f'"{t["company"]}" "{geography}" "credit facility" OR refinancing',
        f'"{t["company"]}" "{geography}" "UCC filing" lender',
        f'"{t["company"]}" "{geography}" "mechanic\'s lien" OR lawsuit',
        f'"{t["company"]}" "{geography}" "debt maturity" OR "covenant"',
        f'"{t["company"]}" "{geography}" "restructuring" OR "special situations"',
        f'"{t["company"]}" "{geography}" "amended credit agreement"',
    ]


def best_roles_for(likely_angle: str) -> List[str]:
    angle = likely_angle.lower()
    if "project finance" in angle or "project capital" in angle or "asset sale" in angle:
        return ["Head of Development", "Project Finance", "Capital Markets", "CFO"]
    if "refinancing" in angle:
        return ["CFO", "VP Finance", "Treasurer", "CEO"]
    if "working capital" in angle or "equipment" in angle:
        return ["CFO", "CEO", "Founder", "President"]
    if "m&a" in angle or "consolidation" in angle:
        return ["Founder", "CEO", "Corporate Development", "Strategy", "PE Sponsor"]
    if "hidden sponsor" in angle:
        return ["Founder", "Head of Development", "Project Development", "Registered Agent"]
    return ["CEO", "Founder", "CFO"]


def generate_people_queries(company: str, likely_angle: str) -> List[str]:
    roles = best_roles_for(likely_angle)
    queries = [f'site:linkedin.com/in "{company}" "{role}"' for role in roles[:5]]
    queries.append(f'site:linkedin.com/in "{company}"')
    return queries


# ----------------------------
# Search backends
# ----------------------------

def serpapi_search(query: str, api_key: str, num: int = 5) -> List[SearchResult]:
    response = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "num": num, "api_key": api_key},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            query=query,
        )
        for item in data.get("organic_results", [])[:num]
    ]


def brave_search(query: str, api_key: str, num: int = 5) -> List[SearchResult]:
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        params={"q": query, "count": num},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("description", ""),
            query=query,
        )
        for item in data.get("web", {}).get("results", [])[:num]
    ]


def run_searches(queries: List[str], max_per_query: int = 4) -> Tuple[List[SearchResult], str]:
    serp_key = get_secret("SERPAPI_KEY")
    brave_key = get_secret("BRAVE_API_KEY")

    results: List[SearchResult] = []
    mode = "manual_links"

    for query in queries:
        try:
            if serp_key:
                results.extend(serpapi_search(query, serp_key, max_per_query))
                mode = "serpapi"
            elif brave_key:
                results.extend(brave_search(query, brave_key, max_per_query))
                mode = "brave"
            else:
                results.append(
                    SearchResult(
                        title="Open search manually",
                        url=google_search_url(query),
                        snippet="No search API key detected. Open this search manually.",
                        query=query,
                    )
                )
        except Exception as exc:
            results.append(
                SearchResult(
                    title="Search error - open manually",
                    url=google_search_url(query),
                    snippet=f"Search API error: {exc}",
                    query=query,
                )
            )

    return dedupe_results(results), mode


def dedupe_results(results: List[SearchResult]) -> List[SearchResult]:
    seen = set()
    clean = []
    for result in results:
        key = (result.url or "").split("?")[0].rstrip("/").lower()
        if key and key not in seen:
            seen.add(key)
            clean.append(result)
    return clean


# ----------------------------
# Extraction and scoring
# ----------------------------

COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'\- ]{2,90}\s(?:LLC|Inc\.?|Corporation|Corp\.?|Company|Co\.?|Holdings|Partners|Energy|Solar|Wind|Storage|Power|Utilities|Infrastructure|Services|Constructors|Contractors|Development|Renewables|Solutions))\b"
)

PROJECT_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'\- ]{2,90}\s(?:Solar|Wind|Storage|Battery|Transmission|Pipeline|Water|Energy)\s(?:Project|LLC|Facility|Farm|Center|Station|Line|Holdings))\b"
)


def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip(" .,-|:")
    junk = [
        "Public Notice", "Planning Commission", "County Board", "Agenda", "Meeting Minutes",
        "Application", "Permit", "Docket", "PDF", "Home",
    ]
    for item in junk:
        name = name.replace(item, "").strip()
    return name


def extract_candidate_name(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet}"
    for regex in [PROJECT_RE, COMPANY_SUFFIX_RE]:
        match = regex.search(text)
        if match:
            return clean_name(match.group(1))
    fallback = re.split(r"[-|:–—]", result.title)[0].strip()
    return clean_name(fallback[:90]) or "Unknown Target"


def evidence_type_from_text(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet} {result.url}".lower()
    if any(k in text for k in ["interconnection", "queue", "ppa", "site permit", "docket", "ferc", "puc", "conditional use permit", "zoning"]):
        return "Permit / docket / queue"
    if any(k in text for k in ["awarded contract", "bid tabulation", "request for proposals", "notice to proceed", "procurement", "contract award"]):
        return "Contract / procurement award"
    if any(k in text for k in ["registered agent", "secretary of state", "business entity", "opencorporates"]):
        return "Entity record / registered agent"
    if any(k in text for k in ["credit facility", "refinancing", "lien", "covenant", "restructuring", "bankruptcy"]):
        return "Debt / distress clue"
    return "Company website / article"


def classify_angle(vertical: str, angle: str, evidence_type: str, text: str) -> str:
    lower = text.lower()
    if evidence_type == "Permit / docket / queue":
        if "renewables" in vertical.lower() or "battery" in vertical.lower():
            return "Project finance / JV / asset sale"
        return "Project capital / strategic partner"
    if evidence_type == "Contract / procurement award":
        return "Working capital / equipment finance / acquisition financing"
    if evidence_type == "Entity record / registered agent":
        return "Hidden sponsor / developer tracing"
    if evidence_type == "Debt / distress clue":
        return "Refinancing / special situations"
    if "acquired" in lower or "acquisition" in lower or "recapital" in lower:
        return "M&A / consolidation"
    if "cfo" in lower or "growth capital" in lower or "expansion" in lower:
        return "Growth capital"
    return "Research lead"


def score_target(evidence_type: str, likely_angle: str, source_snippet: str, url: str) -> Tuple[int, str]:
    score = {
        "Permit / docket / queue": 82,
        "Contract / procurement award": 76,
        "Entity record / registered agent": 70,
        "Debt / distress clue": 78,
        "Company website / article": 58,
    }.get(evidence_type, 50)

    if "Project finance" in likely_angle or "Refinancing" in likely_angle:
        score += 6
    if len(source_snippet or "") > 80:
        score += 5
    if any(domain in url.lower() for domain in ["ferc.gov", "eia.gov", "epa.gov", "sam.gov", ".gov", "misoenergy.org"]):
        score += 5

    score = min(100, score)
    confidence = "High" if score >= 85 else "Medium-High" if score >= 75 else "Medium" if score >= 60 else "Low"
    return score, confidence


def missing_data_for(evidence: str, source_url: str) -> str:
    missing = []
    if not source_url or source_url.startswith("https://www.google.com/search"):
        missing.append("source validation")
    if evidence in {"Permit / docket / queue", "Entity record / registered agent"}:
        missing.append("parent sponsor")
    missing.append("verified decision-maker")
    missing.append("direct contact")
    return ", ".join(missing)


def next_step_for(evidence: str, likely_angle: str) -> str:
    if evidence == "Permit / docket / queue":
        return "Trace project entity to parent sponsor; find Head of Development / Project Finance."
    if evidence == "Contract / procurement award":
        return "Validate contract size/backlog; contact CFO or President."
    if evidence == "Entity record / registered agent":
        return "Use entity/registered agent to identify parent sponsor before outreach."
    if evidence == "Debt / distress clue":
        return "Validate lender/debt issue; contact CFO."
    return "Validate company size, ownership, and transaction trigger."


def build_thesis(company: str, vertical: str, evidence_type: str, likely_angle: str, snippet: str) -> str:
    return (
        f"{company} surfaced through a {evidence_type.lower()} signal. "
        f"In {vertical}, this points toward {likely_angle.lower()}. "
        f"This is an asset/activity-driven lead, so validate the sponsor/owner first, then contact the role most tied to the event. "
        f"Evidence: {snippet[:350]}"
    )


def build_targets_from_results(results: List[SearchResult], vertical: str, angle: str) -> List[Target]:
    targets: List[Target] = []
    for result in results:
        company = extract_candidate_name(result)
        if company.lower() in {"open search manually", "unknown target", "search error"}:
            continue

        evidence = evidence_type_from_text(result)
        likely = classify_angle(vertical, angle, evidence, f"{result.title} {result.snippet}")
        roles = best_roles_for(likely)
        score, confidence = score_target(evidence, likely, result.snippet, result.url)
        people_queries = generate_people_queries(company, likely)
        thesis = build_thesis(company, vertical, evidence, likely, result.snippet)

        targets.append(
            Target(
                priority_score=score,
                confidence=confidence,
                company=company,
                evidence=evidence,
                likely_angle=likely,
                best_roles=", ".join(roles),
                source_url=result.url,
                source_snippet=result.snippet,
                missing_data=missing_data_for(evidence, result.url),
                next_step=next_step_for(evidence, likely),
                linkedin_queries="\n".join(people_queries),
                thesis=thesis,
            )
        )

    seen = set()
    unique: List[Target] = []
    for target in sorted(targets, key=lambda item: item.priority_score, reverse=True):
        key = target.company.lower()
        if key not in seen and len(key) > 3:
            seen.add(key)
            unique.append(target)
    return unique


# ----------------------------
# People discovery
# ----------------------------

LINKEDIN_URL_RE = re.compile(r"linkedin\.com/in/", re.IGNORECASE)
LINKEDIN_NAME_TITLE_RE = re.compile(r"^(.+?)\s+-\s+(.+?)\s+-\s+LinkedIn", re.IGNORECASE)


def infer_role_from_text(text: str) -> str:
    roles = [
        "Chief Financial Officer", "CFO", "CEO", "Founder", "President",
        "Head of Development", "Project Finance", "Capital Markets",
        "Corporate Development", "Strategy", "Vice President", "Director",
        "Owner", "Principal",
    ]
    lower = text.lower()
    found = [role for role in roles if role.lower() in lower]
    return ", ".join(found[:3]) if found else "Unknown role"


def person_fit_score(role_guess: str, likely_angle: str, snippet: str, url: str) -> int:
    text = f"{role_guess} {snippet}".lower()
    score = 30
    if "linkedin.com/in/" in url.lower():
        score += 25

    angle = likely_angle.lower()
    if "project" in angle or "asset sale" in angle:
        if any(key in text for key in ["development", "project finance", "capital markets", "cfo"]):
            score += 30
    elif "refinancing" in angle:
        if any(key in text for key in ["cfo", "finance", "treasurer"]):
            score += 30
    elif "working capital" in angle or "equipment" in angle:
        if any(key in text for key in ["cfo", "president", "ceo", "founder"]):
            score += 30
    elif "m&a" in angle or "consolidation" in angle:
        if any(key in text for key in ["founder", "ceo", "corporate development", "strategy"]):
            score += 30
    else:
        if any(key in text for key in ["ceo", "founder", "cfo", "president"]):
            score += 20

    return min(100, score)


def parse_person_result(result: SearchResult, company: str, likely_angle: str) -> PersonCandidate:
    title = result.title.strip()
    person = title
    role_guess = ""

    match = LINKEDIN_NAME_TITLE_RE.search(title)
    if match:
        person = match.group(1).strip()
        role_guess = match.group(2).strip()
    else:
        parts = re.split(r"\s+\|\s+|\s+-\s+", title)
        if parts:
            person = parts[0].strip()
            role_guess = " / ".join(parts[1:3]).strip()

    if not role_guess:
        role_guess = infer_role_from_text(f"{title} {result.snippet}")

    return PersonCandidate(
        fit_score=person_fit_score(role_guess, likely_angle, result.snippet, result.url),
        company=company,
        person_or_profile=person[:120],
        title_guess=role_guess[:160],
        linkedin_url=result.url,
        source_title=title,
        source_snippet=result.snippet,
        query=result.query,
    )


def find_people_for_targets(targets: List[Target], max_targets: int = 8, max_per_query: int = 3) -> List[PersonCandidate]:
    people: List[PersonCandidate] = []
    for target in targets[:max_targets]:
        queries = generate_people_queries(target.company, target.likely_angle)
        results, _mode = run_searches(queries, max_per_query=max_per_query)
        for result in results:
            if LINKEDIN_URL_RE.search(result.url or ""):
                people.append(parse_person_result(result, target.company, target.likely_angle))

    seen = set()
    unique: List[PersonCandidate] = []
    for person in sorted(people, key=lambda item: item.fit_score, reverse=True):
        key = person.linkedin_url.lower().split("?")[0].rstrip("/")
        if key and key not in seen:
            seen.add(key)
            unique.append(person)
    return unique


# ----------------------------
# Apollo placeholder
# ----------------------------

def apollo_status_message() -> str:
    apollo_key = get_secret("APOLLO_API_KEY")
    if apollo_key:
        return "APOLLO_API_KEY detected. Apollo enrichment can be added in the next version."
    return "No APOLLO_API_KEY detected. Add it later for contact enrichment."


# ----------------------------
# Streamlit UI
# ----------------------------

def main() -> None:
    st.set_page_config(page_title="Energy Target Finder", layout="wide")

    st.title("Energy Infrastructure Target Finder")
    st.caption("Limited filters → company/project targets → people/LinkedIn queries → banker thesis → CSV/email export.")

    with st.sidebar:
        st.header("Search Filters")
        vertical = st.selectbox("Vertical", VERTICALS)
        geography = st.text_input("Geography", GEOGRAPHY_DEFAULT)
        angle = st.selectbox("Target Angle", ANGLES)
        max_per_query = st.slider("Results per query", 2, 10, 4)

        st.divider()
        st.subheader("API Status")
        if get_secret("SERPAPI_KEY"):
            st.success("SERPAPI_KEY detected")
        elif get_secret("BRAVE_API_KEY"):
            st.success("BRAVE_API_KEY detected")
        else:
            st.warning("No search API key detected. Manual search links only.")

        st.info(apollo_status_message())

        run_companies = st.button("1. Find Companies", type="primary", use_container_width=True)
        run_people = st.button("2. Find People for Top Targets", use_container_width=True)

    queries = generate_company_queries(vertical, geography, angle)

    if run_companies:
        with st.spinner("Running company/project discovery..."):
            results, mode = run_searches(queries, max_per_query=max_per_query)
            targets = build_targets_from_results(results, vertical, angle)

        st.session_state["company_results"] = [asdict(result) for result in results]
        st.session_state["targets"] = [asdict(target) for target in targets]
        st.session_state["people"] = []
        st.session_state["mode"] = mode

    st.subheader("Company Discovery Queries")
    st.dataframe(
        pd.DataFrame(
            {
                "query": queries,
                "manual_search_url": [google_search_url(query) for query in queries],
            }
        ),
        use_container_width=True,
        height=230,
    )

    with st.expander("Public source links"):
        st.dataframe(pd.DataFrame(PUBLIC_SOURCES, columns=["source", "url"]), use_container_width=True)

    targets_data = st.session_state.get("targets", [])
    company_results = st.session_state.get("company_results", [])
    people_data = st.session_state.get("people", [])

    if targets_data:
        targets_df = pd.DataFrame(targets_data)

        st.subheader("Companies / Project Sponsors Returned")
        display_cols = [
            "priority_score",
            "confidence",
            "company",
            "evidence",
            "likely_angle",
            "best_roles",
            "source_url",
            "missing_data",
            "next_step",
            "linkedin_queries",
        ]
        st.dataframe(targets_df[display_cols], use_container_width=True, height=430)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Download company targets CSV",
                data=targets_df.to_csv(index=False),
                file_name="company_project_targets.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col2:
            st.link_button(
                "Send Results to TimeX Gmail",
                email_target_list_link(targets_df),
                use_container_width=True,
            )

        st.subheader("Company Detail")
        selected = st.selectbox("Select company", targets_df["company"].tolist())
        row = targets_df[targets_df["company"] == selected].iloc[0]

        st.markdown(f"### {row['company']}")
        st.write(f"**Priority:** {row['priority_score']} | **Confidence:** {row['confidence']}")
        st.write(f"**Likely angle:** {row['likely_angle']}")
        st.write(f"**Best roles:** {row['best_roles']}")
        st.write(f"**Missing data:** {row['missing_data']}")
        st.write(f"**Next step:** {row['next_step']}")
        st.write(row["thesis"])

        st.markdown("#### Public LinkedIn search queries")
        for query in str(row["linkedin_queries"]).split("\n"):
            st.markdown(f"- [{query}]({google_search_url(query)})")

    elif company_results:
        st.info("Search ran, but no structured company names were extracted. Review raw search results.")
        st.dataframe(pd.DataFrame(company_results), use_container_width=True, height=380)
    else:
        st.info("Click **Find Companies** to start.")

    if run_people:
        if not targets_data:
            st.error("Run company discovery first.")
        else:
            target_objects = [Target(**target) for target in targets_data]
            with st.spinner("Running public LinkedIn people discovery for top targets..."):
                people = find_people_for_targets(target_objects, max_targets=8, max_per_query=3)
            st.session_state["people"] = [asdict(person) for person in people]
            people_data = st.session_state["people"]

    st.subheader("People / Public LinkedIn Candidates")
    if people_data:
        people_df = pd.DataFrame(people_data)
        display_people = [
            "fit_score",
            "company",
            "person_or_profile",
            "title_guess",
            "linkedin_url",
            "source_snippet",
            "query",
        ]
        st.dataframe(people_df[display_people], use_container_width=True, height=430)
        st.download_button(
            "Download people CSV",
            data=people_df.to_csv(index=False),
            file_name="people_linkedin_candidates.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.write("Run **Find People for Top Targets** after company discovery. Without a search API key, use the LinkedIn search queries shown above.")


if __name__ == "__main__":
    main()
