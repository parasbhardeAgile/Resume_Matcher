# File: apps/backend/app/services/ats_scoring_service.py

import logging
import re
from typing import Dict, Any, List
from collections import Counter # For finding most common date format

logger = logging.getLogger(__name__)

class AtsScoringService:
    """
    Enhanced ATS scoring service including checks for grammar indicators, date consistency, and length.
    Returns structured suggestions.
    DB-less and embedding-less.
    """
    def __init__(self):
        logger.info("ATS Scoring Service initialized (DB-less)")
        
        # --- START UPDATED ACTION VERBS ---
        # Combined and de-duplicated list from your original code and the provided Harvard PDF 
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
        
        # --- START OPTIMIZATIONS ---
        # Convert to a set for much faster O(1) lookups
        self.action_verbs_set = set(self.action_verbs_list)
        
        # Common adverbs that might start a bullet point
        self.common_adverbs = set([
            "successfully", "effectively", "consistently", "significantly", 
            "actively", "greatly", "strongly", "directly"
        ])
        # --- END OPTIMIZATIONS ---
        
        # Regex patterns
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


    def calculate_ats_score(self, resume_id: str, processed_resume_data: Dict[str, Any], raw_text_content: str = "") -> Dict[str, Any]:
        """Calculates an ATS score with refined checks and returns structured suggestions."""
        logger.info(f"Calculating enhanced ATS score for resume_id: {resume_id}")
        logger.info(f"Received processed_resume_data: {processed_resume_data}")
        if not processed_resume_data:
             return {"resume_id": resume_id, "ats_score": 0, "score_breakdown": {}, "suggestions": {"Overall": ["Processed resume data missing."]}}

        # Define weights (ensure total max = 100)
        criteria_scores = {
            "section_completeness": {"score": 0, "max": 15, "passed": []},
            "contact_info_quality": {"score": 0, "max": 10, "passed": []},
            "profile_summary_quality": {"score": 0, "max": 5, "present": False, "length": 0},
            "keyword_density": {"score": 0, "max": 15, "passed": 0},
            "experience_details_present": {"score": 0, "max": 10, "passed": []},
            "action_verbs": {"score": 0, "max": 15, "passed": 0, "total_bullets": 0},
            "quantifiable_results": {"score": 0, "max": 15, "passed": 0, "total_bullets": 0},
            "bullet_conciseness": {"score": 0, "max": 10, "passed": 0, "total_bullets": 0},
            "grammar_indicators": {"score": 0, "max": 5, "passive_count": 0, "filler_count": 0, "total_bullets": 0},
            "date_consistency": {"score": 0, "max": 5, "consistent": True, "formats_found": []},
            # Total = 100
        }
        max_score = sum(details["max"] for details in criteria_scores.values()) # Should be 100

        # --- Scoring Logic ---

        # 1. Section Completeness
        present_sections = []
        sections_to_check = {"personal_data": "Personal Data", "profile_summary": "Profile Summary", "experiences": "Experience", "education": "Education", "skills": "Skills"}
        points_per_section = criteria_scores["section_completeness"]["max"] / len(sections_to_check)
        for data_key, display_name in sections_to_check.items():
            content = processed_resume_data.get(data_key)
            if content: # Checks for non-empty lists/dicts/strings, non-None
                 criteria_scores["section_completeness"]["score"] += points_per_section
                 present_sections.append(display_name)
        criteria_scores["section_completeness"]["passed"] = present_sections

        # 2. Contact Info Quality
        contact_score = 0
        contact_details_found = []
        personal_data = processed_resume_data.get("personal_data", {})
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
            if linkedin and isinstance(linkedin, str) and ('linkedin.com' in linkedin.lower()):
                 contact_score += criteria_scores["contact_info_quality"]["max"] * 0.2
                 contact_details_found.append("LinkedIn (Found)")
        criteria_scores["contact_info_quality"]["score"] = contact_score
        criteria_scores["contact_info_quality"]["passed"] = contact_details_found

        # 3. Profile Summary Quality
        summary = processed_resume_data.get("profile_summary")
        summary_score = 0
        summary_length = 0
        if summary and isinstance(summary, str) and summary.strip():
            criteria_scores["profile_summary_quality"]["present"] = True
            summary_length = len(summary.split())
            criteria_scores["profile_summary_quality"]["length"] = summary_length
            if 25 <= summary_length <= 75: summary_score = criteria_scores["profile_summary_quality"]["max"]
            elif 10 <= summary_length < 25 or 75 < summary_length <= 100: summary_score = criteria_scores["profile_summary_quality"]["max"] * 0.5
        criteria_scores["profile_summary_quality"]["score"] = summary_score

        # 4. Keyword Density
        extracted_keywords = processed_resume_data.get("extracted_keywords", [])
        keyword_count = len(extracted_keywords) if isinstance(extracted_keywords, list) else 0
        target_keywords = 30
        keyword_ratio = min(keyword_count / target_keywords, 1.0)
        criteria_scores["keyword_density"]["score"] = keyword_ratio * criteria_scores["keyword_density"]["max"]
        criteria_scores["keyword_density"]["passed"] = keyword_count

        # 5-9. Experience/Project/Education Analysis
        experiences = processed_resume_data.get("experiences", [])
        projects = processed_resume_data.get("projects", [])
        combined_entries = [] # Combine sections that have descriptions
        if isinstance(experiences, list): combined_entries.extend(experiences)
        if isinstance(projects, list): combined_entries.extend(projects)
        
        total_bullets = 0
        entries_with_desc = 0
        bullets_with_action_verbs = 0
        bullets_with_numbers = 0
        concise_bullets = 0
        passive_voice_count = 0
        filler_word_count = 0
        date_strings = []
        max_bullet_len_chars = 170

        for entry in combined_entries:
            if not isinstance(entry, dict): continue
            descriptions_raw = entry.get("description", [])
            descriptions = []
            if isinstance(descriptions_raw, str):
                 descriptions = [s.strip() for s in descriptions_raw.split('\n') if s.strip()]
            elif isinstance(descriptions_raw, list):
                 descriptions = [d for d in descriptions_raw if isinstance(d, str)]

            entry_has_desc = False
            if descriptions:
                 entry_has_desc = True
                 for desc in descriptions:
                     if desc.strip():
                         total_bullets += 1
                         desc_clean = desc.strip()
                         
                         # --- START UPDATED ACTION VERB LOGIC ---
                         desc_words = desc_clean.split(" ")
                         first_word = ""
                         if desc_words:
                             first_word = desc_words[0].lower().rstrip('.,:')
                         
                         is_action_verb = False
                         if first_word in self.action_verbs_set: # Use the fast set
                             is_action_verb = True
                         # Check second word if first is a common adverb
                         elif (first_word in self.common_adverbs or (first_word.endswith('ly') and len(first_word) > 3)) and len(desc_words) > 1:
                             second_word = desc_words[1].lower().rstrip('.,:')
                             if second_word in self.action_verbs_set: # Use the fast set
                                 is_action_verb = True
                         
                         if is_action_verb:
                             bullets_with_action_verbs += 1
                         # --- END UPDATED ACTION VERB LOGIC ---

                         if self.number_pattern.search(desc_clean): bullets_with_numbers += 1
                         if len(desc_clean) <= max_bullet_len_chars: concise_bullets += 1
                         if self.passive_voice_pattern.search(desc_clean): passive_voice_count += 1
                         if self.filler_words_pattern.search(desc_clean): filler_word_count += 1

            if entry_has_desc:
                 entries_with_desc += 1
                 entry_name = entry.get("jobTitle") or entry.get("projectName", "Entry")
                 criteria_scores["experience_details_present"]["passed"].append(entry_name)

            start_date = entry.get("start_date") or entry.get("startDate")
            end_date = entry.get("end_date") or entry.get("endDate")
            if isinstance(start_date, str) and start_date.strip(): date_strings.append(start_date.strip())
            if isinstance(end_date, str) and end_date.strip(): date_strings.append(end_date.strip())

        # Collect Education dates separately for consistency check
        edu_entries = processed_resume_data.get("education", [])
        if isinstance(edu_entries, list):
             for entry in edu_entries:
                 if not isinstance(entry, dict): continue
                 start_date = entry.get("start_date") or entry.get("startDate")
                 end_date = entry.get("end_date") or entry.get("endDate")
                 if isinstance(start_date, str) and start_date.strip(): date_strings.append(start_date.strip())
                 if isinstance(end_date, str) and end_date.strip(): date_strings.append(end_date.strip())

        # Score Experience Details Presence
        exp_detail_ratio = entries_with_desc / len(combined_entries) if combined_entries else 0
        criteria_scores["experience_details_present"]["score"] = exp_detail_ratio * criteria_scores["experience_details_present"]["max"]

        # Score Action Verbs
        action_verb_ratio = bullets_with_action_verbs / total_bullets if total_bullets > 0 else 0
        av_score_multiplier = min(action_verb_ratio / 0.8, 1.0)
        criteria_scores["action_verbs"]["score"] = av_score_multiplier * criteria_scores["action_verbs"]["max"]
        criteria_scores["action_verbs"]["passed"] = bullets_with_action_verbs
        criteria_scores["action_verbs"]["total_bullets"] = total_bullets

        # Score Quantifiable Results
        quant_ratio = bullets_with_numbers / total_bullets if total_bullets > 0 else 0
        qr_score_multiplier = min(quant_ratio / 0.35, 1.0)
        criteria_scores["quantifiable_results"]["score"] = qr_score_multiplier * criteria_scores["quantifiable_results"]["max"]
        criteria_scores["quantifiable_results"]["passed"] = bullets_with_numbers
        criteria_scores["quantifiable_results"]["total_bullets"] = total_bullets

        # Score Bullet Conciseness
        concise_ratio = concise_bullets / total_bullets if total_bullets > 0 else 0
        bc_score_multiplier = min(concise_ratio / 0.85, 1.0)
        criteria_scores["bullet_conciseness"]["score"] = bc_score_multiplier * criteria_scores["bullet_conciseness"]["max"]
        criteria_scores["bullet_conciseness"]["passed"] = concise_bullets
        criteria_scores["bullet_conciseness"]["total_bullets"] = total_bullets

        # Score Grammar Indicators
        grammar_max = criteria_scores["grammar_indicators"]["max"]
        passive_penalty_ratio = passive_voice_count / total_bullets if total_bullets > 0 else 0
        filler_penalty_ratio = filler_word_count / total_bullets if total_bullets > 0 else 0
        grammar_score = max(0, grammar_max - (passive_penalty_ratio * grammar_max * 1.5) - (filler_penalty_ratio * grammar_max * 0.75))
        criteria_scores["grammar_indicators"]["score"] = grammar_score
        criteria_scores["grammar_indicators"]["passive_count"] = passive_voice_count
        criteria_scores["grammar_indicators"]["filler_count"] = filler_word_count
        criteria_scores["grammar_indicators"]["total_bullets"] = total_bullets

        # Score Date Consistency
        date_formats_found = [d for d in date_strings if self.date_format_pattern.match(d)]
        consistent_dates = True
        most_common_format_display = "N/A"
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

        if consistent_dates and date_formats_found:
             criteria_scores["date_consistency"]["score"] = criteria_scores["date_consistency"]["max"]
        elif not date_formats_found and date_strings:
             criteria_scores["date_consistency"]["score"] = 0
             consistent_dates = False
        elif not date_strings:
             criteria_scores["date_consistency"]["score"] = criteria_scores["date_consistency"]["max"] * 0.5
             consistent_dates = True
        else: # Inconsistent
             criteria_scores["date_consistency"]["score"] = criteria_scores["date_consistency"]["max"] * 0.3
             consistent_dates = False
        criteria_scores["date_consistency"]["consistent"] = consistent_dates
        criteria_scores["date_consistency"]["formats_found"] = list(set(date_formats_found))


        # --- Calculate Final Score ---
        total_score = sum(details.get("score", 0) for details in criteria_scores.values())
        final_score = int(round(min(total_score, max_score)))

        logger.info(f"Enhanced ATS Score calculated for resume_id {resume_id}: {final_score}")

        structured_suggestions = self._generate_structured_suggestions(criteria_scores, final_score, processed_resume_data)

        return {
            "resume_id": resume_id,
            "ats_score": final_score,
            "score_breakdown": criteria_scores,
            "suggestions": structured_suggestions
        }

    # <<< CORRECTED _generate_structured_suggestions method >>>
    def _generate_structured_suggestions(self, criteria_scores: Dict, final_score: int, processed_resume_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """Generates suggestions categorized by section."""
        suggestions: Dict[str, List[str]] = {
            "Overall": [], "Structure & Sections": [], "Contact Info": [],
            "Profile Summary": [], "Keywords": [], "Experience & Projects": [],
            "Grammar & Style": [], "Education": []
            # Removed "Bullet Conciseness" as a separate category, moved it under Grammar & Style
        }
        score_threshold_good = 85
        score_threshold_medium = 65

        # --- Populate Suggestions by Category (using .get for safety) ---

        # Structure & Sections
        completeness_max = criteria_scores.get("section_completeness", {}).get("max", 15)
        if criteria_scores.get("section_completeness", {}).get("score", 0) < completeness_max:
             missing = []
             passed_sections = criteria_scores.get("section_completeness", {}).get("passed", [])
             if "Personal Data" not in passed_sections: missing.append("Contact Info")
             # Profile Summary is checked below
             if "Experience" not in passed_sections: missing.append("Work Experience/Projects")
             if "Education" not in passed_sections: missing.append("Education")
             if "Skills" not in passed_sections: missing.append("Skills")
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
             if "Profile Summary" not in criteria_scores.get("section_completeness", {}).get("passed", []):
                  suggestions["Structure & Sections"].append("Consider adding a Profile Summary/Objective section near the top.")
             else: # Section present, but no content
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
        if exp_score < exp_max:
             suggestions["Experience & Projects"].append("Ensure every work/project entry includes descriptive bullet points.")

        # Action Verbs (Experience & Projects)
        av_score = criteria_scores.get("action_verbs", {}).get("score", 0)
        av_max = criteria_scores.get("action_verbs", {}).get("max", 15)
        av_passed = criteria_scores.get("action_verbs", {}).get("passed", 0)
        av_total = criteria_scores.get("action_verbs", {}).get("total_bullets", 0)
        if av_total > 0 and av_score < av_max * 0.7:
             suggestions["Experience & Projects"].append(f"Use strong action verbs (e.g., Managed, Developed) to start most ({max(1, av_total - av_passed)} more) bullet points.")

        # Quantifiable Results (Experience & Projects)
        qr_score = criteria_scores.get("quantifiable_results", {}).get("score", 0)
        qr_max = criteria_scores.get("quantifiable_results", {}).get("max", 15)
        qr_passed = criteria_scores.get("quantifiable_results", {}).get("passed", 0)
        qr_total = criteria_scores.get("quantifiable_results", {}).get("total_bullets", 0)
        target_quant_bullets = max(1, int(qr_total * 0.35))
        if qr_total > 0 and qr_score < qr_max * 0.6:
             suggestions["Experience & Projects"].append(f"Quantify achievements more. Add numbers/metrics to showcase impact (aim for ~{target_quant_bullets} bullets).")

        # Grammar & Style
        
        # --- Bullet Conciseness Suggestion (moved here) ---
        bc_score = criteria_scores.get("bullet_conciseness", {}).get("score", 0)
        bc_max = criteria_scores.get("bullet_conciseness", {}).get("max", 10)
        bc_total = criteria_scores.get("bullet_conciseness", {}).get("total_bullets", 0) # Now defined before use
        if bc_total > 0 and bc_score < bc_max * 0.8:
             suggestions["Grammar & Style"].append("Keep bullet points concise (ideally 1-2 lines, under 170 characters) for easy scanning.")
        # --- End Bullet Conciseness Suggestion ---

        grammar_score = criteria_scores.get("grammar_indicators", {}).get("score", 0)
        grammar_max = criteria_scores.get("grammar_indicators", {}).get("max", 5)
        passive_count = criteria_scores.get("grammar_indicators", {}).get("passive_count", 0)
        filler_count = criteria_scores.get("grammar_indicators", {}).get("filler_count", 0)
        if grammar_score < grammar_max * 0.8:
            if passive_count > 0:
                 suggestions["Grammar & Style"].append(f"Avoid passive voice ({passive_count} instance(s) found). Rephrase actively (e.g., 'Managed team' instead of 'Team was managed').")
            if filler_count > 0:
                 suggestions["Grammar & Style"].append(f"Replace weaker phrases like 'responsible for' or 'assisted with' ({filler_count} instance(s) found) with direct action verbs describing your contribution.")

        if not criteria_scores.get("date_consistency", {}).get("consistent", True):
             suggestions["Grammar & Style"].append("Use a consistent date format (e.g., MM/YYYY or Month YYYY) throughout all sections (Experience, Education).")

        # Overall Feedback
        has_specific_suggestions = any(len(sug_list) > 0 for cat, sug_list in suggestions.items() if cat != "Overall")

        if final_score < score_threshold_medium :
             suggestions["Overall"].append("This resume needs significant improvement for ATS compatibility. Focus on the suggestions provided in each category.")
        elif final_score < score_threshold_good: # Medium score
             if has_specific_suggestions:
                 suggestions["Overall"].append("Good start! This resume is quite ATS-friendly. Addressing the specific suggestions can make it even stronger.")
             else:
                 suggestions["Overall"].append("Good structure and content! Generally ATS-friendly. Minor tweaks could improve it further.")
        else: # Good score
             if has_specific_suggestions:
                 suggestions["Overall"].append("Excellent score! Your resume aligns well with ATS best practices. Addressing the minor suggestions below will make it even better.")
             else:
                 suggestions["Overall"].append("Excellent! Your resume follows ATS best practices effectively.")


        # Filter out empty categories
        final_suggestions = {cat: sug_list for cat, sug_list in suggestions.items() if sug_list}
        return final_suggestions