# File: apps/backend/app/services/ats_scoring_service.py

import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from collections import Counter # For finding most common date format
import json # Ensure json is imported
import math # Ensure math is imported

logger = logging.getLogger(__name__)

# --- Thresholds ---
THRESHOLD_GOOD = 80 # Percentage score to be considered 'Good' or 'Strong' / Pass
THRESHOLD_MEDIUM = 60 # Percentage score to be considered 'Okay' / Pass


class AtsScoringService:
    """
    Enhanced ATS scoring service including checks for grammar indicators, date consistency, and length.
    Returns structured output specifically for the frontend report UI.
    DB-less and embedding-less.
    """
    def __init__(self):
        logger.info("ATS Scoring Service initialized (DB-less)")
        # --- Action Verbs, Regex Patterns, etc. ---
        self.action_verbs_list = [
            "accelerated", "accomplished", "achieved", "acted", "adapted", "added",
            "addressed", "administered", "advised", "allocated", "analyzed", "appraised",
            "approved", "arbitrated", "arranged", "assembled", "assessed", "assigned",
            "assisted", "attained", "audited", "authored", "balanced", "broadened",
            "budgeted", "calculated", "cataloged", "centralized", "chaired", "changed",
            "clarified", "classified", "coached", "collaborated", "collected",
            "communicated", "compiled", "completed", "composed", "computed",
            "conceptualized", "conceived", "concluded", "conducted", "consolidated",
            "constructed", "contracted", "controlled", "convinced", "coordinated",
            "corresponded", "counseled", "created", "critiqued", "customized",
            "defined", "delegated", "delivered", "demonstrated", "demystified",
            "derived", "designed", "determined", "developed", "devised", "diagnosed",
            "directed", "discovered", "dispatched", "documented", "drafted", "earned",
            "edited", "educated", "enabled", "encouraged", "engineered", "energized",
            "enhanced", "enlisted", "ensured", "established", "evaluated", "examined",
            "executed", "expanded", "expedited", "explained", "extracted", "fabricated",
            "facilitated", "familiarized", "fashioned", "forecasted", "formed",
            "formulated", "founded", "gained", "gathered", "generated", "guided",
            "handled", "headed", "identified", "illustrated", "impacted", "implemented",
            "improved", "increased", "influenced", "informed", "initiated", "inspected",
            "installed", "instituted", "instructed", "integrated", "interpreted",
            "interviewed", "introduced", "invented", "investigated", "launched",
            "lectured", "led", "liaised", "maintained", "managed", "marketed",
            "mastered", "maximized", "mediated", "minimized", "modeled", "moderated",
            "monitored", "motivated", "negotiated", "operated", "optimized",
            "orchestrated", "organized", "originated", "overhauled", "oversaw",
            "participated", "performed", "persuaded", "planned", "predicted",
            "prepared", "presented", "prioritized", "processed", "produced",
            "programmed", "projected", "promoted", "proposed", "proved", "provided",
            "publicized", "published", "purchased", "recommended", "reconciled",
            "recorded", "recruited", "redesigned", "reduced", "referred", "regulated",
            "rehabilitated", "reinforced", "remodeled", "reorganized", "repaired",
            "reported", "represented", "researched", "resolved", "retrieved",
            "reviewed", "revised", "revitalized", "rewrote", "scheduled", "screened",
            "selected", "served", "set goals", "shaped", "simplified", "sold",
            "solved", "spoke", "spearheaded", "specified", "standardized", "steered",
            "stimulated", "streamlined", "strengthened", "structured", "studied",
            "suggested", "summarized", "supervised", "supported", "surpassed",
            "surveyed", "synthesized", "systematized", "tabulated", "taught",
            "tested", "trained", "translated", "unified", "updated", "upgraded",
            "utilized", "validated", "verbalized", "verified", "visualized", "wrote"
        ]
        self.action_verbs_set = set(self.action_verbs_list)
        self.common_adverbs = set([
            "successfully", "effectively", "consistently", "significantly",
            "actively", "greatly", "strongly", "directly"
        ])
        self.number_pattern = re.compile(
             r'\d+%?|'
             r'\$\d{1,3}(?:,\d{3})*(?:\.\d+)?|'
             r'\b\d+\b(?!\s*-\s*\d)(?:\s*(?:million|thousand|hundred|billion|k))?|'
             r'\b(?:over|under|approx(?:imately)?|more than|less than|up to)\s+\d+\b',
             re.IGNORECASE
        )
        self.email_pattern = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
        self.phone_pattern = re.compile(r"[\d\s\-\+\(\).]{7,}")
        self.passive_voice_pattern = re.compile(r'\b(am|is|are|was|were|been|being)\s+\w+ed\b', re.IGNORECASE)
        self.filler_words_pattern = re.compile(r'\b(responsible for|duties included|assisted with|worked on|involved in)\b', re.IGNORECASE)
        self.date_format_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{4}-\d{2}$|^\d{2}/\d{4}$|^\w+\s+\d{4}$|Present", re.IGNORECASE)


    def calculate_ats_score(self, resume_id: str, processed_resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates ATS score, generates suggestions, and structures output for frontend.
        """
        logger.info(f"Calculating ATS score for resume_id: {resume_id}")

        try:
            data_string = json.dumps(processed_resume_data, indent=2, ensure_ascii=False)
            logger.debug(f"--- Received processed_resume_data for {resume_id}: ---\n{data_string}") # DEBUG Level
        except Exception as e:
            logger.error(f"Error logging processed_resume_data: {e}")

        if not processed_resume_data:
             logger.warning(f"Processed resume data is empty for {resume_id}.")
             return {
                 "resume_id": resume_id, "ats_score": 0, "error": "Processed resume data missing.",
                 "score_breakdown_for_sidebar": {}, "report_details": []
             }

        try:
            # --- Step 1: Calculate raw scores using the CORRECT keys ---
            criteria_scores = self._calculate_criteria_scores(processed_resume_data)

            # --- Step 2: Calculate Final Score ---
            total_score = sum(details.get("score", 0) for details in criteria_scores.values())
            max_score = sum(details.get("max", 0) for details in criteria_scores.values())
            if max_score != 100: logger.warning(f"Max possible score from criteria_scores is {max_score}, not 100.")

            final_score = int(round(min(max(0, total_score), 100)))
            logger.info(f"Raw ATS Score calculated for {resume_id}: {final_score}")
            logger.debug(f"Score breakdown used for structuring: {json.dumps(criteria_scores, indent=2)}")

            # --- Step 3: Generate text suggestions ---
            suggestions = self._generate_structured_suggestions(criteria_scores, final_score, processed_resume_data)

            # --- Step 4: Structure final response for frontend (Sidebar + Report Cards) ---
            structured_output = self._structure_frontend_response(final_score, criteria_scores, suggestions)

            return {
                "resume_id": resume_id,
                **structured_output # Merge {ats_score, score_breakdown_for_sidebar, report_details}
            }
        except Exception as e:
            logger.error(f"Error during score calculation/structuring for {resume_id}: {e}", exc_info=True)
            return {
                 "resume_id": resume_id, "ats_score": 0, "error": f"An unexpected error occurred during scoring: {e}",
                 "score_breakdown_for_sidebar": {}, "report_details": []
             }

    # --- Calculation logic with FIXED KEY ACCESS ---
    def _calculate_criteria_scores(self, processed_resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method to calculate the raw scores for each criterion. Uses CORRECTED keys."""
        criteria_scores = {
            "section_completeness": {"score": 0, "max": 15, "passed": []},
            "contact_info_quality": {"score": 0, "max": 10, "passed": []},
            "profile_summary_quality": {"score": 0, "max": 5, "present": False, "length": 0},
            "keyword_density": {"score": 0, "max": 15, "passed": 0, "keywords_found": []},
            "experience_details_present": {"score": 0, "max": 10, "passed": [], "total_entries": 0},
            "action_verbs": {"score": 0, "max": 15, "passed": 0, "total_bullets": 0},
            "quantifiable_results": {"score": 0, "max": 15, "passed": 0, "total_bullets": 0},
            "bullet_conciseness": {"score": 0, "max": 10, "passed": 0, "total_bullets": 0},
            "grammar_indicators": {"score": 0, "max": 5, "passive_count": 0, "filler_count": 0, "total_bullets": 0},
            "date_consistency": {"score": 0, "max": 5, "consistent": True, "formats_found": [], "has_dates": False},
        }
        max_score_check = sum(details["max"] for details in criteria_scores.values())
        if max_score_check != 100: logger.warning(f"_calculate_criteria_scores: Max score adds up to {max_score_check}, not 100.")

        # --- Scoring Logic (Using CORRECTED keys: "Title Case" top-level, camelCase inner) ---

        # 1. Section Completeness (Using "Title Case" keys)
        present_sections = []
        sections_to_check = {
            "Personal Data": "Personal Data", "Profile Summary": "Profile Summary",
            "Experiences": "Experience", "Education": "Education", "Skills": "Skills",
            "Projects": "Projects"
        }
        points_per_section = criteria_scores["section_completeness"]["max"] / len(sections_to_check) if sections_to_check and criteria_scores["section_completeness"]["max"] > 0 else 0
        for data_key, display_name in sections_to_check.items():
            content = processed_resume_data.get(data_key) # Use "Title Case" key
            if content is not None:
                is_present_and_non_empty = not isinstance(content, (list, dict)) or bool(content)
                if is_present_and_non_empty:
                    criteria_scores["section_completeness"]["score"] += points_per_section
                    present_sections.append(display_name)
        criteria_scores["section_completeness"]["passed"] = present_sections
        criteria_scores["section_completeness"]["score"] = min(criteria_scores["section_completeness"]["score"], criteria_scores["section_completeness"]["max"])

        # 2. Contact Info Quality (Using "Title Case" key)
        contact_score = 0
        contact_details_found = []
        personal_data = processed_resume_data.get("Personal Data", {}) # Use "Title Case" key
        if isinstance(personal_data, dict):
            email = personal_data.get("email")
            phone = personal_data.get("phone")
            linkedin = personal_data.get("linkedin")
            if email and isinstance(email, str) and self.email_pattern.match(email):
                 contact_score += criteria_scores["contact_info_quality"]["max"] * 0.4
                 contact_details_found.append("Email (Valid Format)")
            if phone and isinstance(phone, str) and self.phone_pattern.search(phone):
                 contact_score += criteria_scores["contact_info_quality"]["max"] * 0.4
                 contact_details_found.append("Phone (Found)")
            if linkedin and isinstance(linkedin, str) and 'linkedin.com' in linkedin.lower() and not linkedin.lower() == 'string':
                 contact_score += criteria_scores["contact_info_quality"]["max"] * 0.2
                 contact_details_found.append("LinkedIn (Found)")
        criteria_scores["contact_info_quality"]["score"] = contact_score
        criteria_scores["contact_info_quality"]["passed"] = contact_details_found

        # 3. Profile Summary Quality (Using "Title Case" key)
        summary = processed_resume_data.get("Profile Summary") # Use "Title Case" key
        summary_score = 0; summary_length = 0; summary_present = False
        if summary and isinstance(summary, str) and summary.strip():
            summary_present = True
            summary_words = summary.split()
            summary_length = len(summary_words)
            if 25 <= summary_length <= 75: summary_score = criteria_scores["profile_summary_quality"]["max"]
            elif 10 <= summary_length < 25 or 75 < summary_length <= 100: summary_score = criteria_scores["profile_summary_quality"]["max"] * 0.5
        criteria_scores["profile_summary_quality"]["score"] = summary_score
        criteria_scores["profile_summary_quality"]["present"] = summary_present
        criteria_scores["profile_summary_quality"]["length"] = summary_length

        # 4. Keyword Density (Using "Title Case" keys)
        extracted_keywords = processed_resume_data.get("Extracted Keywords", []) # Use "Title Case" key
        skills_list = processed_resume_data.get("Skills", []) # Use "Title Case" key
        all_keywords = set(k for k in extracted_keywords if isinstance(k, str))
        if isinstance(skills_list, list):
             for skill_entry in skills_list:
                 skill_name = None
                 if isinstance(skill_entry, dict):
                      skill_name = skill_entry.get("skillName") or skill_entry.get("skill_name")
                 if skill_name and isinstance(skill_name, str):
                      all_keywords.add(skill_name)
        keyword_count = len(all_keywords)
        target_keywords = 30
        keyword_ratio = min(keyword_count / target_keywords, 1.0) if target_keywords > 0 else 0
        criteria_scores["keyword_density"]["score"] = keyword_ratio * criteria_scores["keyword_density"]["max"]
        criteria_scores["keyword_density"]["passed"] = keyword_count
        criteria_scores["keyword_density"]["keywords_found"] = sorted(list(all_keywords))

        # 5-9. Experience/Project Analysis (Using "Title Case" keys)
        experiences = processed_resume_data.get("Experiences", []) # Use "Title Case" key
        projects = processed_resume_data.get("Projects", [])     # Use "Title Case" key
        combined_entries = []
        if isinstance(experiences, list): combined_entries.extend(experiences)
        if isinstance(projects, list): combined_entries.extend(projects)

        criteria_scores["experience_details_present"]["total_entries"] = len(combined_entries)
        total_bullets = 0; entries_with_desc = 0; bullets_with_action_verbs = 0; bullets_with_numbers = 0; concise_bullets = 0; passive_voice_count = 0; filler_word_count = 0; date_strings = []
        max_bullet_len_chars = 170

        for entry in combined_entries:
            if not isinstance(entry, dict): continue
            descriptions_raw = entry.get("description") # Use camelCase
            descriptions = []
            if isinstance(descriptions_raw, str): descriptions = [s.strip() for s in descriptions_raw.split('\n') if s.strip()]
            elif isinstance(descriptions_raw, list): descriptions = [d for d in descriptions_raw if isinstance(d, str) and d.strip()]

            entry_has_desc = bool(descriptions)
            if entry_has_desc:
                 entries_with_desc += 1
                 entry_name = entry.get("jobTitle") or entry.get("projectName", "Entry") # Use camelCase
                 criteria_scores["experience_details_present"]["passed"].append(entry_name)
                 for desc in descriptions:
                     total_bullets += 1; desc_clean = desc; desc_words = desc_clean.split(" ")
                     first_word = desc_words[0].lower().rstrip('.,:') if desc_words else ""
                     is_action_verb = False
                     if first_word in self.action_verbs_set: is_action_verb = True
                     elif (first_word in self.common_adverbs or (first_word.endswith('ly') and len(first_word)>3)) and len(desc_words) > 1:
                         second_word = desc_words[1].lower().rstrip('.,:')
                         if second_word in self.action_verbs_set: is_action_verb = True
                     if is_action_verb: bullets_with_action_verbs += 1
                     if self.number_pattern.search(desc_clean): bullets_with_numbers += 1
                     if len(desc_clean) <= max_bullet_len_chars: concise_bullets += 1
                     if self.passive_voice_pattern.search(desc_clean): passive_voice_count += 1
                     if self.filler_words_pattern.search(desc_clean): filler_word_count += 1

            start_date = entry.get("startDate") # Use camelCase
            end_date = entry.get("endDate")     # Use camelCase
            if isinstance(start_date, str) and start_date.strip(): date_strings.append(start_date.strip())
            if isinstance(end_date, str) and end_date.strip(): date_strings.append(end_date.strip())

        # Collect Education dates
        edu_entries = processed_resume_data.get("Education", []) # Use "Title Case" key
        if isinstance(edu_entries, list):
             for entry in edu_entries:
                 if not isinstance(entry, dict): continue
                 start_date = entry.get("startDate") # Use camelCase
                 end_date = entry.get("endDate")     # Use camelCase
                 if isinstance(start_date, str) and start_date.strip(): date_strings.append(start_date.strip())
                 if isinstance(end_date, str) and end_date.strip(): date_strings.append(end_date.strip())

        # --- Update criteria_scores based on counts ---
        criteria_scores["experience_details_present"]["score"] = (entries_with_desc / len(combined_entries) if combined_entries else 0) * criteria_scores["experience_details_present"]["max"]
        criteria_scores["action_verbs"]["total_bullets"] = total_bullets
        criteria_scores["quantifiable_results"]["total_bullets"] = total_bullets
        criteria_scores["bullet_conciseness"]["total_bullets"] = total_bullets
        criteria_scores["grammar_indicators"]["total_bullets"] = total_bullets
        if total_bullets > 0:
            criteria_scores["action_verbs"]["passed"] = bullets_with_action_verbs
            criteria_scores["action_verbs"]["score"] = min(bullets_with_action_verbs / total_bullets / 0.8, 1.0) * criteria_scores["action_verbs"]["max"]
            criteria_scores["quantifiable_results"]["passed"] = bullets_with_numbers
            criteria_scores["quantifiable_results"]["score"] = min(bullets_with_numbers / total_bullets / 0.35, 1.0) * criteria_scores["quantifiable_results"]["max"]
            criteria_scores["bullet_conciseness"]["passed"] = concise_bullets
            criteria_scores["bullet_conciseness"]["score"] = min(concise_bullets / total_bullets / 0.85, 1.0) * criteria_scores["bullet_conciseness"]["max"]
            grammar_max = criteria_scores["grammar_indicators"]["max"]
            passive_penalty_ratio = passive_voice_count / total_bullets
            filler_penalty_ratio = filler_word_count / total_bullets
            grammar_score = max(0, grammar_max - (passive_penalty_ratio * grammar_max * 1.5) - (filler_penalty_ratio * grammar_max * 0.75))
            criteria_scores["grammar_indicators"]["score"] = grammar_score
            criteria_scores["grammar_indicators"]["passive_count"] = passive_voice_count
            criteria_scores["grammar_indicators"]["filler_count"] = filler_word_count

        # Date Consistency
        criteria_scores["date_consistency"]["has_dates"] = bool(date_strings)
        date_formats_found = [d for d in date_strings if self.date_format_pattern.match(d)]
        consistent_dates = True; most_common_format_display = "N/A"
        if len(date_formats_found) >= 1:
            format_categories = []
            for d in date_formats_found:
                 d_upper = d.upper()
                 if d_upper == "PRESENT": format_categories.append("PRESENT")
                 elif re.match(r"^\d{4}-\d{2}-\d{2}$", d): format_categories.append("YYYY-MM-DD")
                 elif re.match(r"^\d{4}-\d{2}$", d): format_categories.append("YYYY-MM")
                 elif re.match(r"^\d{2}/\d{4}$", d): format_categories.append("MM/YYYY")
                 elif re.match(r"^\w+\s+\d{4}$", d): format_categories.append("Month YYYY")
                 else: format_categories.append("Unknown")
            format_counts = Counter(cat for cat in format_categories if cat != 'Unknown')
            if format_counts:
                 valid_format_types = set(format_counts.keys()) - {'PRESENT'}
                 if len(valid_format_types) > 1: consistent_dates = False
                 most_common_format_display = format_counts.most_common(1)[0][0]
        elif date_strings:
             consistent_dates = False
        if consistent_dates and date_formats_found: criteria_scores["date_consistency"]["score"] = criteria_scores["date_consistency"]["max"]
        elif not date_strings: criteria_scores["date_consistency"]["score"] = criteria_scores["date_consistency"]["max"] * 0.5; consistent_dates = True
        else: criteria_scores["date_consistency"]["score"] = 0; consistent_dates = False
        criteria_scores["date_consistency"]["consistent"] = consistent_dates
        criteria_scores["date_consistency"]["formats_found"] = list(set(date_formats_found)) # Store matched formats only


        logger.debug(f"Calculated criteria scores (using corrected keys): {json.dumps(criteria_scores, indent=2)}")
        return criteria_scores


    # --- *** UPDATED: Method to structure results for Sidebar AND Report Details *** ---
    def _structure_frontend_response(self, final_score: int, criteria_scores: Dict, suggestions: Dict[str, List[str]]) -> Dict[str, Any]:
        """Takes raw scores and suggestions, returns structured dict for frontend UI."""

        # --- Helper to calculate percentage and status/color ---
        def get_status_color_perc(score: Optional[float], max_score: Optional[float]) -> Tuple[int | None, str, str]:
            if score is None or max_score is None or max_score == 0:
                return None, "Info", "default"
            percentage = math.ceil(min(max(score / max_score, 0), 1) * 100)
            if percentage >= THRESHOLD_GOOD: return percentage, "Strong", "success"
            if percentage >= THRESHOLD_MEDIUM: return percentage, "Okay", "warning"
            return percentage, "Needs Improvement", "error"

        # Helper to calculate percentage only
        def calculate_percentage(score: Optional[float], max_score: Optional[float]) -> int | None:
            if score is None or max_score is None or max_score == 0:
                return None
            percentage = math.ceil(min(max(score / max_score, 0), 1) * 100)
            return percentage

        # --- Build Sidebar Data ---
        sidebar_categories = []
        total_issues_count = 0

        # --- 1. CONTENT Category (Sidebar) ---
        content_sub_items = []
        content_scores_sum = 0
        content_max_sum = 0
        content_sub_items.append({"text": "ATS Parse Rate", "status": "pass"})
        qr_item = criteria_scores.get("quantifiable_results")
        if qr_item:
            qr_perc = calculate_percentage(qr_item.get("score"), qr_item.get("max"))
            qr_status = "pass" if qr_perc is not None and qr_perc >= THRESHOLD_MEDIUM else "fail"
            content_sub_items.append({"text": "Quantifying Impact", "status": qr_status})
            if qr_item.get("max", 0) > 0:
                 content_scores_sum += qr_item.get("score", 0); content_max_sum += qr_item.get("max", 0)
            if qr_status == "fail": total_issues_count += 1
        content_sub_items.append({"text": "Repetition", "status": "info"}) # No check for this yet
        gi_item = criteria_scores.get("grammar_indicators")
        if gi_item:
             gi_perc = calculate_percentage(gi_item.get("score"), gi_item.get("max"))
             gi_status = "pass" if gi_perc is not None and gi_perc >= THRESHOLD_GOOD else "fail"
             content_sub_items.append({"text": "Spelling & Grammar", "status": gi_status})
             if gi_item.get("max", 0) > 0:
                  content_scores_sum += gi_item.get("score", 0); content_max_sum += gi_item.get("max", 0)
             if gi_status == "fail": total_issues_count += 1
        content_percentage = calculate_percentage(content_scores_sum, content_max_sum)
        sidebar_categories.append({"title": "CONTENT", "percentage": content_percentage, "sub_items": content_sub_items})

        # --- 2. SECTION Category (Sidebar) ---
        section_sub_items = []; section_scores_sum = 0; section_max_sum = 0
        es_item = criteria_scores.get("section_completeness")
        if es_item:
            es_perc = calculate_percentage(es_item.get("score"), es_item.get("max"))
            es_status = "pass" if es_perc is not None and es_perc >= 90 else "fail"
            section_sub_items.append({"text": "Essential Sections", "status": es_status})
            if es_item.get("max", 0) > 0:
                 section_scores_sum += es_item.get("score", 0); section_max_sum += es_item.get("max", 0)
            if es_status == "fail": total_issues_count += 1
        ci_item = criteria_scores.get("contact_info_quality")
        if ci_item:
            ci_perc = calculate_percentage(ci_item.get("score"), ci_item.get("max"))
            ci_status = "pass" if ci_perc is not None and ci_perc >= 80 else "fail"
            section_sub_items.append({"text": "Contact Information", "status": ci_status})
            if ci_item.get("max", 0) > 0:
                 section_scores_sum += ci_item.get("score", 0); section_max_sum += ci_item.get("max", 0)
            if ci_status == "fail": total_issues_count += 1
        section_percentage = calculate_percentage(section_scores_sum, section_max_sum)
        sidebar_categories.append({"title": "SECTION", "percentage": section_percentage, "sub_items": section_sub_items})

        # --- 3. ATS ESSENTIALS Category (Sidebar) ---
        ats_sub_items = []; ats_pass_count = 0; ats_total_checkable = 0
        ats_sub_items.append({"text": "File Format & Size", "status": "pass"}) # Assumed pass
        ats_sub_items.append({"text": "Design", "status": "info"}) # No check for this
        ci_item = criteria_scores.get("contact_info_quality") # Reuse
        email_status = "fail"; ats_total_checkable += 1
        if ci_item and "Email (Valid Format)" in ci_item.get("passed", []):
            email_status = "pass"; ats_pass_count += 1
        ats_sub_items.append({"text": "Email Address", "status": email_status})
        if email_status == "fail": total_issues_count += 1
        linkedin_status = "fail"; ats_total_checkable += 1
        if ci_item and "LinkedIn (Found)" in ci_item.get("passed", []):
            linkedin_status = "pass"; ats_pass_count += 1
        ats_sub_items.append({"text": "Hyperlink in Header", "status": linkedin_status})
        if linkedin_status == "fail": total_issues_count += 1
        ats_percentage = calculate_percentage(ats_pass_count, ats_total_checkable)
        sidebar_categories.append({"title": "ATS ESSENTIALS", "percentage": ats_percentage, "sub_items": ats_sub_items})

        # --- 4. TAILORING Category (Sidebar) ---
        tailoring_sub_items = [
            {"text": "Hard Skills", "status": "info"},
            {"text": "Soft Skills", "status": "info"},
            {"text": "Action Verbs", "status": "info"},
            {"text": "Tailored Title", "status": "info"}
        ]
        sidebar_categories.append({"title": "TAILORING", "percentage": None, "sub_items": tailoring_sub_items})

        # --- Final Sidebar Output ---
        sidebar_output = {
             "overall_score": final_score,
             "total_issues": total_issues_count,
             "categories": sidebar_categories
        }

        # --- *** UPDATED: Build Report Details (Main Content) *** ---
        report_details_output = []

        # --- Card 1: Summary ---
        try:
             summary_item = criteria_scores.get("profile_summary_quality", {})
             summary_perc, summary_status, summary_color = get_status_color_perc(summary_item.get("score"), summary_item.get("max"))
             summary_points = []
             if summary_item.get("present", False):
                 summary_points.append({"text": "Summary is present.", "isGood": True})
                 # Check length score
                 if summary_item.get("score", 0) == summary_item.get("max", 5):
                      summary_points.append({"text": "Good length (25-75 words).", "isGood": True})
                 else:
                      summary_points.append({"text": "Summary length is too short (< 25 words) or too long (> 75 words).", "isGood": False})
             else:
                 summary_points.append({"text": "Profile Summary section is missing or empty.", "isGood": False})

             report_details_output.append({
                "id": "summary", "icon": "📝", "title": "Summary",
                "status": summary_status, "color": summary_color,
                "points": summary_points,
                "ai_suggestions": suggestions.get("Profile Summary", []) # Get simple text suggestions
             })
        except Exception as e: logger.error(f"Error building Summary report detail: {e}")

        # --- Card 2: Work Experience ---
        try:
            av_item = criteria_scores.get("action_verbs", {})
            qr_item = criteria_scores.get("quantifiable_results", {})
            exp_details_item = criteria_scores.get("experience_details_present", {})
            
            # Combine scores for overall status
            exp_score = av_item.get("score", 0) + qr_item.get("score", 0) + exp_details_item.get("score", 0)
            exp_max = av_item.get("max", 0) + qr_item.get("max", 0) + exp_details_item.get("max", 0)
            exp_perc, exp_status, exp_color = get_status_color_perc(exp_score, exp_max)

            exp_points = []
            # Check for descriptions
            exp_entries_count = exp_details_item.get("total_entries", 0)
            desc_entries_count = len(exp_details_item.get("passed", []))
            if exp_entries_count > 0:
                 exp_points.append({
                     "text": f"Found descriptions for {desc_entries_count} of {exp_entries_count} entries.",
                     "isGood": desc_entries_count == exp_entries_count
                 })
            # Check action verbs
            av_perc = calculate_percentage(av_item.get("score"), av_item.get("max"))
            exp_points.append({
                 "text": "Uses strong action verbs to start bullet points.",
                 "isGood": av_perc is not None and av_perc >= THRESHOLD_MEDIUM
            })
            # Check quantifying impact
            qr_perc = calculate_percentage(qr_item.get("score"), qr_item.get("max"))
            exp_points.append({
                 "text": "Includes quantifiable achievements (numbers, $, %).",
                 "isGood": qr_perc is not None and qr_perc >= THRESHOLD_MEDIUM
            })

            report_details_output.append({
                "id": "experience", "icon": "💼", "title": "Work Experience",
                "status": exp_status, "color": exp_color,
                "points": exp_points,
                "ai_suggestions": suggestions.get("Experience & Projects", []) # Get simple text suggestions
            })
        except Exception as e: logger.error(f"Error building Experience report detail: {e}")

        # --- Card 3: Skills ---
        try:
            kw_item = criteria_scores.get("keyword_density", {})
            kw_perc, kw_status, kw_color = get_status_color_perc(kw_item.get("score"), kw_item.get("max"))
            kw_points = []
            kw_count = kw_item.get("passed", 0)
            if kw_count >= 15:
                 kw_points.append({"text": f"Good mix of skills/keywords found ({kw_count}).", "isGood": True})
            elif kw_count >= 5:
                 kw_points.append({"text": f"Includes some relevant skills ({kw_count}), but could add more.", "isGood": True})
            else:
                 kw_points.append({"text": f"Low skill/keyword count ({kw_count}). Add more relevant terms.", "isGood": False})

            report_details_output.append({
                "id": "skills", "icon": "🛠️", "title": "Skills",
                "status": kw_status, "color": kw_color,
                "points": kw_points,
                "ai_suggestions": suggestions.get("Keywords", []) # Get simple text suggestions
            })
        except Exception as e: logger.error(f"Error building Skills report detail: {e}")

        # --- Card 4: Formatting & Style ---
        try:
            bc_item = criteria_scores.get("bullet_conciseness", {})
            gi_item = criteria_scores.get("grammar_indicators", {})
            dc_item = criteria_scores.get("date_consistency", {})

            style_score = bc_item.get("score", 0) + gi_item.get("score", 0) + dc_item.get("score", 0)
            style_max = bc_item.get("max", 0) + gi_item.get("max", 0) + dc_item.get("max", 0)
            style_perc, style_status, style_color = get_status_color_perc(style_score, style_max)

            style_points = []
            bc_perc = calculate_percentage(bc_item.get("score"), bc_item.get("max"))
            style_points.append({
                 "text": "Bullet points are concise and easy to read.",
                 "isGood": bc_perc is not None and bc_perc >= THRESHOLD_GOOD
            })
            gi_perc = calculate_percentage(gi_item.get("score"), gi_item.get("max"))
            style_points.append({
                 "text": "Uses active voice and strong phrasing.",
                 "isGood": gi_perc is not None and gi_perc >= THRESHOLD_GOOD
            })
            style_points.append({
                 "text": "Date formats are consistent.",
                 "isGood": dc_item.get("consistent", False)
            })

            report_details_output.append({
                "id": "style", "icon": "🎨", "title": "Formatting & Style",
                "status": style_status, "color": style_color,
                "points": style_points,
                "ai_suggestions": suggestions.get("Grammar & Style", []) # Get simple text suggestions
            })
        except Exception as e: logger.error(f"Error building Style report detail: {e}")


        # --- Return combined structure ---
        return {
             "ats_score": final_score,
             "score_breakdown_for_sidebar": sidebar_output,
             "report_details": report_details_output # Now contains the array of card data
        }


    # --- Suggestion generation logic exactly as provided by user ---
    def _generate_structured_suggestions(self, criteria_scores: Dict, final_score: int, processed_resume_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """Generates suggestions categorized by section."""
        # (Keep the exact implementation provided by the user)
        suggestions: Dict[str, List[str]] = {
            "Overall": [], "Structure & Sections": [], "Contact Info": [],
            "Profile Summary": [], "Keywords": [], "Experience & Projects": [],
            "Grammar & Style": [], "Education": []
        }
        score_threshold_good = 85
        score_threshold_medium = 65
        
        # --- Populate Suggestions (using corrected keys) ---
        
        # Structure & Sections
        completeness_max = criteria_scores.get("section_completeness", {}).get("max", 15)
        passed_sections_list = criteria_scores.get("section_completeness", {}).get("passed", [])
        if criteria_scores.get("section_completeness", {}).get("score", 0) < completeness_max - 0.1: # Added tolerance
             missing = []
             # Check display names
             if "Personal Data" not in passed_sections_list: missing.append("Contact Info")
             if "Experience" not in passed_sections_list: missing.append("Work Experience/Projects")
             if "Education" not in passed_sections_list: missing.append("Education")
             if "Skills" not in passed_sections_list: missing.append("Skills")
             if "Projects" not in passed_sections_list: missing.append("Projects") # Check for projects
             if missing:
                 suggestions["Structure & Sections"].append(f"Missing or unclear standard sections: {', '.join(missing)}. Use clear headers.")

        # Contact Info
        contact_score = criteria_scores.get("contact_info_quality", {}).get("score", 0)
        contact_max = criteria_scores.get("contact_info_quality", {}).get("max", 10)
        contact_passed = criteria_scores.get("contact_info_quality", {}).get("passed", [])
        if contact_score < contact_max * 0.8:
             missing_contact = []
             if "Email (Valid Format)" not in contact_passed: missing_contact.append("valid Email")
             if "Phone (Found)" not in contact_passed: missing_contact.append("Phone Number")
             if missing_contact:
                 suggestions["Contact Info"].append(f"Include essential, correctly formatted details: {', '.join(missing_contact)}.")
        if "LinkedIn (Found)" not in contact_passed:
             suggestions["Contact Info"].append("Consider adding a professional LinkedIn profile link.")

        # Profile Summary
        summary_score = criteria_scores.get("profile_summary_quality", {}).get("score", 0)
        summary_max = criteria_scores.get("profile_summary_quality", {}).get("max", 5)
        summary_present = criteria_scores.get("profile_summary_quality", {}).get("present", False)
        summary_length = criteria_scores.get("profile_summary_quality", {}).get("length", 0)
        if not summary_present:
             if "Profile Summary" not in passed_sections_list: # Check display name
                 suggestions["Structure & Sections"].append("Consider adding a Profile Summary/Objective section near the top.")
             else:
                 suggestions["Profile Summary"].append("Add a brief Profile Summary (2-4 sentences) to highlight key qualifications.")
        elif summary_score < summary_max:
             if summary_length < 25:
                 suggestions["Profile Summary"].append("Expand your summary slightly (aim for 2-4 sentences) to better introduce key skills.")
             elif summary_length > 75:
                 suggestions["Profile Summary"].append("Condense your summary to 2-4 concise sentences focusing on strongest qualifications.")

        # Keywords
        kw_score = criteria_scores.get("keyword_density", {}).get("score", 0)
        kw_max = criteria_scores.get("keyword_density", {}).get("max", 15)
        kw_count = criteria_scores.get("keyword_density", {}).get("passed", 0)
        if kw_count < 10:
            suggestions["Keywords"].append("Keyword count is low. Ensure technical skills, tools, software, industry terms are clearly listed/described.")
        elif kw_score < kw_max * 0.7:
            suggestions["Keywords"].append(f"Keyword usage ({kw_count} found) could be improved. Integrate more relevant terms naturally into Summary and Experience.")

        # Experience & Projects
        exp_score = criteria_scores.get("experience_details_present", {}).get("score", 0)
        exp_max = criteria_scores.get("experience_details_present", {}).get("max", 10)
        if exp_score < exp_max - 0.1:
             suggestions["Experience & Projects"].append("Ensure every work/project entry includes descriptive bullet points.")

        # Action Verbs (Experience & Projects)
        av_score = criteria_scores.get("action_verbs", {}).get("score", 0)
        av_max = criteria_scores.get("action_verbs", {}).get("max", 15)
        av_passed = criteria_scores.get("action_verbs", {}).get("passed", 0)
        av_total = criteria_scores.get("action_verbs", {}).get("total_bullets", 0)
        if av_total > 0 and av_score < av_max * 0.7:
             suggestions["Experience & Projects"].append(f"Use strong action verbs (e.g., Managed, Developed) to start most ({max(1, int(av_total*0.8) - av_passed)} more) bullet points.")

        # Quantifiable Results (Experience & Projects)
        qr_score = criteria_scores.get("quantifiable_results", {}).get("score", 0)
        qr_max = criteria_scores.get("quantifiable_results", {}).get("max", 15)
        qr_passed = criteria_scores.get("quantifiable_results", {}).get("passed", 0)
        qr_total = criteria_scores.get("quantifiable_results", {}).get("total_bullets", 0)
        target_quant_bullets = max(1, int(qr_total * 0.35))
        if qr_total > 0 and qr_score < qr_max * 0.6:
             suggestions["Experience & Projects"].append(f"Quantify achievements more. Add numbers/metrics to showcase impact (aim for ~{target_quant_bullets} bullets).")

        # Grammar & Style
        bc_score = criteria_scores.get("bullet_conciseness", {}).get("score", 0)
        bc_max = criteria_scores.get("bullet_conciseness", {}).get("max", 10)
        bc_total = criteria_scores.get("bullet_conciseness", {}).get("total_bullets", 0)
        if bc_total > 0 and bc_score < bc_max * 0.8:
            suggestions["Grammar & Style"].append("Keep bullet points concise (ideally 1-2 lines, under 170 characters) for easy scanning.")

        grammar_score = criteria_scores.get("grammar_indicators", {}).get("score", 0)
        grammar_max = criteria_scores.get("grammar_indicators", {}).get("max", 5)
        passive_count = criteria_scores.get("grammar_indicators", {}).get("passive_count", 0)
        filler_count = criteria_scores.get("grammar_indicators", {}).get("filler_count", 0)
        if grammar_score < grammar_max * 0.8 or passive_count > 0 or filler_count > 0:
            if passive_count > 0:
                 suggestions["Grammar & Style"].append(f"Avoid passive voice ({passive_count} instance(s) found). Rephrase actively (e.g., 'Managed team' instead of 'Team was managed').")
            if filler_count > 0:
                 suggestions["Grammar & Style"].append(f"Replace weaker phrases like 'responsible for' or 'assisted with' ({filler_count} instance(s) found) with direct action verbs describing your contribution.")

        if not criteria_scores.get("date_consistency", {}).get("consistent", True):
             formats = criteria_scores.get("date_consistency", {}).get("formats_found", [])
             suggestion_text = "Use a consistent date format (e.g., MM/YYYY or Month YYYY) throughout all sections (Experience, Education)."
             if formats:
                 valid_formats = [f for f in formats if self.date_format_pattern.match(f)]
                 unique_valid = sorted(list(set(valid_formats)))
                 suggestion_text += f" Found formats like: {', '.join(unique_valid[:3])}{'...' if len(unique_valid) > 3 else ''}."
             suggestions["Grammar & Style"].append(suggestion_text)

        # Education Section
        education_entries = processed_resume_data.get("Education", []) # Use correct key
        missing_edu_details = False
        if isinstance(education_entries, list):
             for edu in education_entries:
                 if isinstance(edu, dict):
                     if not edu.get("institution") or not edu.get("degree"):
                         missing_edu_details = True; break
        if missing_edu_details:
             suggestions["Education"].append("Ensure all education entries include both the institution name and the degree/qualification obtained.")

        # Overall Feedback
        has_specific_suggestions = any(len(sug_list) > 0 for cat, sug_list in suggestions.items() if cat != "Overall")
        if final_score < score_threshold_medium :
             suggestions["Overall"].append("This resume needs significant improvement for ATS compatibility. Focus on the suggestions provided in each category.")
        elif final_score < score_threshold_good:
             if has_specific_suggestions:
                 suggestions["Overall"].append("Good start! This resume is reasonably ATS-friendly. Addressing the specific suggestions can make it much stronger.")
             else:
                 suggestions["Overall"].append("Good structure and content! Generally ATS-friendly. Minor refinements could improve it further.")
        else:
             if has_specific_suggestions:
                 suggestions["Overall"].append("Excellent score! Your resume aligns well with ATS best practices. Addressing the minor suggestions below will perfect it.")
             else:
                 suggestions["Overall"].append("Excellent! Your resume follows ATS best practices effectively.")

        final_suggestions = {cat: sug_list for cat, sug_list in suggestions.items() if sug_list}
        return final_suggestions