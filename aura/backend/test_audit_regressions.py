import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import automation
from backend.ai_engine import (
    _build_direct_live_data_context,
    _build_live_answer_hint,
    _build_multi_question_live_context,
    _build_output_intent_context,
    _build_live_search_query,
    _direct_source_backed_answer,
    _detect_output_formats,
    _detect_emotional_state,
    _detect_user_language_preference,
    _extract_matchups_from_live_context,
    _fetch_ipl_standings_context,
    _fetch_news_direct_context,
    _humor_policy,
    _language_instruction,
    _needs_structured_table,
    _parse_ipl_standings_rows,
    _preferred_live_source_profile,
    _split_live_questions,
    _needs_live_web_context,
    build_social_intelligence_context,
)
from backend.artifact_engine import (
    artifact_markdown,
    create_requested_artifacts,
    requested_artifact_formats,
    sanitize_model_artifact_placeholders,
)
from backend.main import (
    _normalize_whatsapp_allowed_contact,
    _speaker_access_level,
    build_browser_prompt_plan,
    extract_send_message_details,
    hash_password,
    normalize_auth_email,
    verify_password,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRect:
    def __init__(self, left: int, top: int, right: int, bottom: int):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeElement:
    def __init__(self, text: str, rect: FakeRect, control_type: str = "Text"):
        self._text = text
        self._rect = rect
        self.element_info = SimpleNamespace(control_type=control_type, name=text)

    def window_text(self):
        return self._text

    def rectangle(self):
        return self._rect


class AuditRegressionTests(unittest.TestCase):
    def test_whatsapp_parser_allows_only_amma_aliases(self):
        self.assertEqual(
            extract_send_message_details("open whatsapp desktop and send hi to Amma"),
            ("hi", "Amma"),
        )
        self.assertEqual(
            extract_send_message_details("send good morning message to mummy on whatsapp"),
            ("good morning", "mummy"),
        )
        self.assertEqual(_normalize_whatsapp_allowed_contact("mummy on whatsapp desktop"), "Amma")
        self.assertIsNone(_normalize_whatsapp_allowed_contact("Amma Home"))

    def test_whatsapp_plan_rejects_unsafe_contact(self):
        allowed = build_browser_prompt_plan("open whatsapp desktop and send hi to Amma")
        self.assertEqual(
            allowed["steps"][-1]["payload"],
            {"contact": "Amma", "message": "hi"},
        )

        rejected = build_browser_prompt_plan("open whatsapp desktop and send hi to Amma Home")
        self.assertTrue(rejected["needs_clarification"])
        self.assertEqual(rejected["steps"], [])

    def test_whatsapp_ui_matching_requires_exact_visible_contact(self):
        window = object()
        elements = [
            FakeElement("Amma Home", FakeRect(30, 260, 260, 305), "ListItem"),
            FakeElement("Amma", FakeRect(30, 320, 260, 365), "ListItem"),
        ]

        with (
            patch.object(automation, "_iter_descendants", return_value=elements),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            match = automation._find_whatsapp_contact_element(window, ["Amma"])
            self.assertIsNotNone(match)
            self.assertEqual(match.window_text(), "Amma")

    def test_whatsapp_chat_header_requires_exact_contact(self):
        window = object()
        wrong_header = [FakeElement("Amma Home", FakeRect(360, 35, 520, 70), "Text")]
        right_header = [FakeElement("Amma", FakeRect(360, 35, 520, 70), "Text")]

        with (
            patch.object(automation, "_iter_descendants", return_value=wrong_header),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            self.assertFalse(automation._is_whatsapp_chat_open(window, ["Amma"]))

        with (
            patch.object(automation, "_iter_descendants", return_value=right_header),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            self.assertTrue(automation._is_whatsapp_chat_open(window, ["Amma"]))

    def test_speaker_relationship_access_levels(self):
        self.assertEqual(_speaker_access_level("amma"), "trusted")
        self.assertEqual(_speaker_access_level("mother"), "trusted")
        self.assertEqual(_speaker_access_level("owner"), "owner")
        self.assertEqual(_speaker_access_level("guest"), "guest")
        self.assertEqual(_speaker_access_level("unknown"), "guest")

    def test_social_intelligence_context_adapts_mother_relationship(self):
        context = build_social_intelligence_context(
            {
                "display_name": "Amma",
                "relationship_to_owner": "mother",
                "access_level": "trusted",
                "closeness_level": "close",
                "language_preference": "telugu_english",
                "notes": "Yogesh's mother",
            },
            "I am worried about his food",
            "stressed",
        )

        self.assertIn("Active speaker: Amma", context)
        self.assertIn("Relationship to owner Yogesh: mother", context)
        self.assertIn("Closeness level: close", context)
        self.assertIn("food, health, rest", context)
        self.assertIn("Telugu + English", context)
        self.assertIn("Mood state: stressed", context)
        self.assertIn("protected actions need owner approval", context)

    def test_social_intelligence_context_defaults_to_owner_for_chat_session(self):
        context = build_social_intelligence_context(None, "continue my project work", None)

        self.assertIn("Active speaker: Yogesh", context)
        self.assertIn("Relationship to owner Yogesh: owner", context)
        self.assertIn("Closeness level: close", context)
        self.assertIn("personal assistant plus close companion", context)

    def test_emotional_state_detection_from_text(self):
        self.assertEqual(_detect_emotional_state("I am very tired today"), "tired")
        self.assertEqual(_detect_emotional_state("this exam pressure is stressful"), "stressed")
        self.assertEqual(_detect_emotional_state("awesome super excited"), "excited")

    def test_friend_humor_depends_on_closeness_and_mood(self):
        close_friend = build_social_intelligence_context(
            {
                "display_name": "Rahul",
                "relationship_to_owner": "friend",
                "access_level": "trusted",
                "closeness_level": "close",
                "communication_style": "college banter",
                "language_preference": "hinglish",
                "interaction_count": 31,
            },
            "bro I finally finished the assignment",
            "happy",
        )

        self.assertIn("playful teasing is allowed", close_friend)
        self.assertIn("Hinglish", close_friend)
        self.assertIn("college-style banter", close_friend)

        stressed_friend_policy = _humor_policy("friend", "close", "stressed")
        self.assertIn("Humor: off", stressed_friend_policy)

    def test_social_context_includes_recent_speaker_history_subtly(self):
        context = build_social_intelligence_context(
            {
                "display_name": "Rahul",
                "relationship_to_owner": "friend",
                "access_level": "trusted",
                "closeness_level": "normal",
                "recent_interactions": [
                    {"role": "user", "content": "My lab exam is tomorrow", "mood_state": "stressed"},
                    {"role": "assistant", "content": "Let's revise the key parts calmly.", "mood_state": "stressed"},
                ],
            },
            "hey",
            "neutral",
        )

        self.assertIn("Recent per-speaker interaction history", context)
        self.assertIn("My lab exam is tomorrow", context)
        self.assertIn("Use recent per-speaker history subtly", context)

    def test_language_detection_handles_ten_telugu_inputs(self):
        telugu_cases = [
            "ఏమైంది రా ఈరోజు silent గా ఉన్నావ్",
            "నాకు ఈ topic explain cheppu",
            "ఇప్పుడు class lo emi jarigindi",
            "సరే anna project chudu",
            "ఎక్కడ issue undi cheppandi",
            "em chestunnav ra",
            "naku exam tension undi cheppu",
            "ippudu ela prepare avvali",
            "sare inka next task cheppu",
            "assignment lo emi mistake undi",
        ]

        for text in telugu_cases:
            with self.subTest(text=text):
                self.assertEqual(_detect_user_language_preference(text, "english"), "telugu_english")

    def test_language_detection_handles_ten_hindi_inputs(self):
        hindi_cases = [
            "क्या हुआ आज थोड़ा tired लग रहे हो",
            "मुझे यह topic समझाओ",
            "आज class में क्या हुआ",
            "ठीक है अब next task बताओ",
            "कहाँ issue आ रहा है",
            "kya hua aaj thoda tired ho",
            "mujhe ye topic samjhao",
            "kaise prepare karna hai batao",
            "aap theek ho kya",
            "bas ab ruk jao",
        ]

        for text in hindi_cases:
            with self.subTest(text=text):
                self.assertEqual(_detect_user_language_preference(text, "english"), "hindi")

    def test_language_detection_handles_ten_mixed_language_inputs(self):
        mixed_cases = [
            ("Bro today class lo sir Hindi lo explain chesadu", "telugu_english"),
            ("Exam ki vellali but mood ledu", "telugu_english"),
            ("Project lo issue undi can you check", "telugu_english"),
            ("Sare now open browser and chudu", "telugu_english"),
            ("Naku output ravatledu please debug", "telugu_english"),
            ("Bro kya scene hai today class lo", "hindi"),
            ("Aaj assignment submit karna hai okay", "hindi"),
            ("Mujhe code samjhao but simple English lo", "hindi"),
            ("Ruko bas one minute I will tell", "hindi"),
            ("Kya bro college life chal raha hai", "hindi"),
        ]

        for text, expected in mixed_cases:
            with self.subTest(text=text):
                self.assertEqual(_detect_user_language_preference(text, "english"), expected)

    def test_language_instruction_prevents_english_fallback_for_indian_languages(self):
        hindi_instruction = _language_instruction("hindi", "hindi")
        telugu_instruction = _language_instruction("telugu_english", "telugu_english")

        self.assertIn("Devanagari", hindi_instruction)
        self.assertIn("Indian Hindi", hindi_instruction)
        self.assertIn("Do not answer only in English", hindi_instruction)
        self.assertIn("Telugu + English", telugu_instruction)
        self.assertIn("Indian Telugu speaker", telugu_instruction)
        self.assertIn("do not answer only in English", telugu_instruction)

    def test_voice_recognition_language_buttons_bias_asr_before_english(self):
        voice_hook = (PROJECT_ROOT / "src/hooks/useVoice.ts").read_text(encoding="utf-8")

        self.assertIn("if (preference === 'hindi') return ['hi-IN', 'en-IN'];", voice_hook)
        self.assertIn(
            "if (preference === 'telugu_english') return ['te-IN', 'en-IN', 'hi-IN'];",
            voice_hook,
        )
        self.assertIn("return ['en-IN', 'en-US'];", voice_hook)
        self.assertNotIn("return ['en-IN', 'te-IN', 'hi-IN'];", voice_hook)

    def test_mixed_voice_recognition_keeps_selected_indian_language_active(self):
        voice_hook = (PROJECT_ROOT / "src/hooks/useVoice.ts").read_text(encoding="utf-8")

        self.assertIn("languageMode === 'mixed'", voice_hook)
        self.assertIn("voiceLanguage === 'hindi'", voice_hook)
        self.assertIn("voiceLanguage === 'telugu_english'", voice_hook)
        self.assertNotIn("languageMode === 'mixed'\n                  ? 'en-IN'", voice_hook)

    def test_frontend_speech_paths_use_one_shared_audio_guard(self):
        guard = (PROJECT_ROOT / "src/lib/audioPlaybackGuard.ts").read_text(encoding="utf-8")
        voice_hook = (PROJECT_ROOT / "src/hooks/useVoice.ts").read_text(encoding="utf-8")
        chat_thread = (
            PROJECT_ROOT / "src/app/chat-interface/components/ChatThread.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("claimAkanshaAudio", guard)
        self.assertIn("hardCancelBrowserSpeech", guard)
        self.assertIn("settleBrowserSpeechCancel", guard)
        self.assertIn("@/lib/audioPlaybackGuard", voice_hook)
        self.assertIn("@/lib/audioPlaybackGuard", chat_thread)
        self.assertNotIn("window.__akanshaAudioOwner", voice_hook)
        self.assertNotIn("window.__akanshaAudioOwner", chat_thread)

    def test_avatar_shader_disables_portrait_mouth_bulge(self):
        avatar_stage = (
            PROJECT_ROOT / "src/components/assistant/AssistantAvatarStage.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("p.z += mouth * 0.0", avatar_stage)
        self.assertIn("p.y -= mouth * 0.0", avatar_stage)
        self.assertIn("p.y -= jaw * 0.0", avatar_stage)
        self.assertNotIn("p.z += mouth * (", avatar_stage)
        self.assertNotIn("jaw * uSpeech", avatar_stage)

    def test_isolated_3d_interface_uses_phoneme_blendshapes_and_silence_lock(self):
        avatar_interface = (
            PROJECT_ROOT / "src/components/assistant/Akansha3DInterface.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("audioStream: MediaStream;", avatar_interface)
        self.assertIn("currentPhoneme: string;", avatar_interface)
        self.assertIn("currentEmotion: string;", avatar_interface)
        self.assertIn("target.jawOpen = 0.15;", avatar_interface)
        self.assertIn("target.mouthPucker = 0.1;", avatar_interface)
        self.assertIn("target.jawOpen = 0;", avatar_interface)
        self.assertIn("target.mouthPucker = 0.25;", avatar_interface)
        self.assertIn("target.jawOpen = 0.65;", avatar_interface)
        self.assertIn("target.mouthFunnel = 0.4;", avatar_interface)
        self.assertIn("target.mouthSmileLeft = 0.15;", avatar_interface)
        self.assertIn("target.mouthSmileRight = 0.15;", avatar_interface)
        self.assertIn("AudioContext", avatar_interface)
        self.assertIn("currentTime", avatar_interface)
        self.assertIn("TimedPhonemeChunk", avatar_interface)
        self.assertIn("currentBlendshapesRef.current.jawOpen = 0;", avatar_interface)
        self.assertIn("currentBlendshapesRef.current.mouthFunnel = 0;", avatar_interface)
        self.assertIn("currentBlendshapesRef.current.mouthPucker = 0;", avatar_interface)
        self.assertNotIn("ProceduralSafetyFallback", avatar_interface)
        self.assertNotIn("<sphereGeometry", avatar_interface)
        self.assertNotIn("speakingVolume", avatar_interface)
        self.assertNotIn("getByteFrequencyData", avatar_interface)

    def test_media_followup_sets_volume_and_clicks_requested_result(self):
        plan = build_browser_prompt_plan("play third song and play at 60 volume")

        self.assertEqual(plan["steps"][0], {"action": "set_volume", "payload": {"amount": 60}})
        self.assertEqual(
            plan["steps"][1],
            {"action": "click_youtube_result", "target": "3", "payload": {"amount": 3}},
        )

    def test_youtube_search_play_uses_first_result_by_default(self):
        plan = build_browser_prompt_plan("open youtube and play bahubali 2 songs")

        self.assertEqual(plan["steps"][0]["action"], "open_youtube_song")
        self.assertEqual(plan["steps"][0]["target"], "bahubali 2 songs")
        self.assertEqual(plan["steps"][0]["payload"]["index"], 1)
        self.assertTrue(plan["steps"][0]["payload"]["play"])

    def test_active_window_shortcuts_are_planned(self):
        save_plan = build_browser_prompt_plan("save this")
        self.assertEqual(save_plan["steps"], [{"action": "hotkey", "payload": {"keys": ["ctrl", "s"]}}])

        scroll_plan = build_browser_prompt_plan("scroll down")
        self.assertEqual(
            scroll_plan["steps"],
            [{"action": "scroll", "target": "down", "payload": {"direction": "down", "amount": 6}}],
        )

    def test_form_fill_waits_for_submit_confirmation(self):
        plan = build_browser_prompt_plan(
            "open example.com and fill name Yogesh email yogesh@example.com phone 9999999999 before submitting popup notification"
        )

        self.assertEqual(plan["steps"][0], {"action": "open_url", "target": "example.com"})
        self.assertEqual(plan["steps"][2]["action"], "type_sequence")
        self.assertEqual(
            plan["steps"][2]["payload"]["values"],
            ["Yogesh", "yogesh@example.com", "9999999999"],
        )
        self.assertFalse(plan["steps"][2]["payload"]["submit"])
        self.assertEqual(plan["steps"][3]["action"], "notify_user")

    def test_submit_followup_presses_enter(self):
        plan = build_browser_prompt_plan("okay all okay submit")

        self.assertEqual(
            plan["steps"],
            [{"action": "press_key", "target": "enter", "payload": {"key": "enter"}}],
        )

    def test_compound_youtube_scroll_and_close_present_tab(self):
        scroll_plan = build_browser_prompt_plan("open youtube website and scroll one by one")
        self.assertEqual(scroll_plan["steps"][0], {"action": "open_url", "target": "https://youtube.com"})
        self.assertEqual(scroll_plan["steps"][1]["action"], "wait")
        self.assertEqual(
            scroll_plan["steps"][2],
            {"action": "scroll", "target": "down", "payload": {"direction": "down", "amount": 3}},
        )

        close_plan = build_browser_prompt_plan("close the present YouTube tab")
        self.assertEqual(close_plan["steps"], [{"action": "close_tab"}])

    def test_live_web_context_detection_for_current_questions(self):
        self.assertTrue(_needs_live_web_context("what are the latest AI news today"))
        self.assertTrue(_needs_live_web_context("search the internet for current weather"))
        self.assertTrue(_needs_live_web_context("who won the match"))
        self.assertTrue(_needs_live_web_context("what is the highest score"))
        self.assertTrue(_needs_live_web_context("silver and gold per gram"))
        self.assertTrue(_needs_live_web_context("ebullion silver rate"))
        self.assertFalse(_needs_live_web_context("explain recursion simply"))

    def test_live_ipl_search_query_is_date_anchored(self):
        query = _build_live_search_query("what are the teams having an IPL match today")

        self.assertIn("IPL", query)
        self.assertIn("match teams", query)
        self.assertRegex(query, r"\b20\d{2}\b")

    def test_ipl_points_table_prompts_force_live_structured_table_answering(self):
        prompt = "Give me the complete points table 2026 IPL"
        query = _build_live_search_query(prompt)
        context = _build_output_intent_context(prompt)

        self.assertTrue(_needs_live_web_context(prompt))
        self.assertTrue(_needs_structured_table(prompt))
        self.assertIn("points table", query)
        self.assertIn("standings", query)
        self.assertIn("clean Markdown table", context)
        self.assertIn("Never tell the user to visit a website", context)
        self.assertIn("Do not use confident words", context)
        self.assertIn("Confidence score means source coverage only", context)

    def test_ipl_standings_parser_extracts_verified_rows_without_guessing(self):
        sample = (
            "1 Royal Challengers Bengaluru 13 9 4 18+1.065 "
            "2 Gujarat Titans 13 8 5 16+0.400 "
            "3 Sunrisers Hyderabad 13 8 5 16+0.350"
        )
        rows = _parse_ipl_standings_rows(sample)

        self.assertEqual(rows[0]["team"], "Royal Challengers Bengaluru")
        self.assertEqual(rows[0]["points"], "18")
        self.assertEqual(rows[0]["nrr"], "+1.065")
        self.assertEqual(rows[1]["team"], "Gujarat Titans")

    @patch(
        "backend.ai_engine._read_url",
        return_value=(
            "1 Royal Challengers Bengaluru 13 9 4 18+1.065 "
            "2 Gujarat Titans 13 8 5 16+0.400 "
            "3 Sunrisers Hyderabad 13 8 5 16+0.350 "
            "4 Punjab Kings 13 6 6 13+0.227 "
            "5 Rajasthan Royals 12 6 6 12+0.027 "
            "6 Chennai Super Kings 13 6 7 12-0.016 "
            "7 Delhi Capitals 13 6 7 12-0.871 "
            "8 Kolkata Knight Riders 12 5 6 11-0.038 "
            "9 Mumbai Indians 12 4 8 8-0.504 "
            "10 Lucknow Super Giants 12 4 8 8-0.701"
        ),
    )
    def test_ipl_points_table_context_contains_source_verified_table(self, _mock_read):
        context = _fetch_ipl_standings_context("generate points table ipl 2026")

        self.assertIn("DIRECT LIVE DATA: IPL 2026 points table extracted", context)
        self.assertIn("| Royal Challengers Bengaluru | 13 | 9 | 4 | 0 | 18 | +1.065 | Verified from source |", context)
        self.assertIn("Do not invent missing teams", context)

    def test_source_backed_ipl_table_answer_uses_only_parsed_rows(self):
        live_context = (
            "DIRECT LIVE DATA: IPL 2026 points table extracted from Test Source (https://example.com/table). "
            "Fetched at Tuesday, May 19, 2026, 9:08 PM IST. Use exactly these rows.\n"
            "| Pos | Team | P | W | L | NR | Pts | NRR | Source status |\n"
            "|---:|---|---:|---:|---:|---:|---:|---:|---|\n"
            "| 1 | Royal Challengers Bengaluru | 13 | 9 | 4 | 0 | 18 | +1.065 | Verified from source |\n"
            "| 2 | Gujarat Titans | 13 | 8 | 5 | 0 | 16 | +0.400 | Verified from source |"
        )

        answer = _direct_source_backed_answer("generate points table ipl 2026", live_context)

        self.assertIn("Royal Challengers Bengaluru", answer)
        self.assertIn("Gujarat Titans", answer)
        self.assertIn("I did not add confidence", answer)
        self.assertNotIn("Mumbai Indians | 10", answer)

    def test_source_backed_news_answer_labels_items_as_source_reported(self):
        live_context = (
            "DIRECT LIVE DATA: India current news RSS/news feeds fetched at Tuesday, May 19, 2026, 9:10 PM IST. "
            "Use these source-attributed headlines.\n"
            "- The Hindu National: Parliament passes example bill [Tue, 19 May 2026 10:00:00 +0530] - Short summary.\n"
            "- Indian Express India: State update headline [Tue, 19 May 2026 09:00:00 +0530]"
        )

        answer = _direct_source_backed_answer("latest India news today", live_context)

        self.assertIn("| Source | Headline | Published | Status |", answer)
        self.assertIn("Source-reported, not independently confirmed", answer)
        self.assertNotIn("confidence", answer.lower())

    def test_output_format_detection_for_generated_files(self):
        prompt = "Generate Excel, PDF, PNG, JPG, CSV, JSON and invoice report for IPL stats"

        self.assertEqual(
            set(_detect_output_formats(prompt)),
            {"xlsx", "pdf", "png", "jpg", "csv", "json"},
        )
        self.assertEqual(
            set(requested_artifact_formats(prompt)),
            {"xlsx", "pdf", "png", "jpg", "csv", "json"},
        )
        self.assertIn("pdf", requested_artifact_formats("Create invoice for web design service"))
        self.assertIn("pdf", requested_artifact_formats("Make formula sheet notes for Java"))
        self.assertIn("pptx", requested_artifact_formats("Generate 10 PowerPoints about Java"))
        self.assertIn("jpg", requested_artifact_formats("Create a jpc image for the workflow"))
        self.assertEqual(
            set(requested_artifact_formats("Generate all file formats for this report")),
            {"pdf", "docx", "pptx", "xlsx", "csv", "json", "png", "jpg", "md", "zip"},
        )

    def test_sandbox_download_links_are_removed_before_real_artifacts(self):
        cleaned = sanitize_model_artifact_placeholders(
            "I made it: [Download PDF](sandbox:/fake.pdf)\n\nGenerated summary stays here."
        )

        self.assertNotIn("sandbox:", cleaned)
        self.assertNotIn("Download PDF", cleaned)
        self.assertIn("Generated summary stays here.", cleaned)

    def test_openrouter_auto_model_is_configurable(self):
        ai_engine = (PROJECT_ROOT / "backend/ai_engine.py").read_text(encoding="utf-8")
        env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn('OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/auto")', ai_engine)
        self.assertIn("model=OPENROUTER_MODEL", ai_engine)
        self.assertNotIn('model="openai/gpt-4o-mini"', ai_engine)
        self.assertIn("OPENROUTER_MODEL=openrouter/auto", env_example)

    def test_java_pdf_prompt_generates_requested_pages_and_complete_code(self):
        prompt = (
            "generate pdf containing code of java all top questions required for tcs placements "
            "10 pages atleast along with complete code in Java, along with comments for each question, "
            "give at least 30 coding questions"
        )
        artifacts = create_requested_artifacts(prompt, "Short outline only.")
        pdf_artifact = next(artifact for artifact in artifacts if artifact["format"] == "pdf")
        pdf_path = PROJECT_ROOT / "generated_artifacts" / pdf_artifact["name"]

        self.assertTrue(pdf_path.exists())
        if fitz := __import__("fitz"):
            document = fitz.open(pdf_path)
            text = "\n".join(page.get_text() for page in document)
            self.assertGreaterEqual(document.page_count, 10)
            document.close()
            self.assertIn("Question 30", text)
            self.assertIn("Complete Java code with comments", text)
            self.assertIn("public class Solution", text)

    def test_document_generation_prompt_is_not_treated_as_browser_automation(self):
        automation_commands = (PROJECT_ROOT / "src/lib/automationCommands.ts").read_text(encoding="utf-8")

        self.assertIn("ARTIFACT_GENERATION_PATTERNS", automation_commands)
        self.assertIn("return false", automation_commands)
        self.assertIn("pdf|pptx?", automation_commands)

    def test_artifact_engine_creates_downloadable_structured_outputs(self):
        response = (
            "| Team | Pts | Status |\n"
            "|---|---:|---|\n"
            "| Punjab Kings | 17 | Verified |\n"
            "| Mumbai Indians | 16 | Verified |\n"
        )

        artifacts = create_requested_artifacts("Generate Excel and CSV of IPL stats", response)
        formats = {artifact["format"] for artifact in artifacts}
        markdown = artifact_markdown(artifacts)

        self.assertEqual(formats, {"xlsx", "csv"})
        self.assertIn("| Format | Download |", markdown)
        for artifact in artifacts:
            self.assertTrue((PROJECT_ROOT / "generated_artifacts" / artifact["name"]).exists())

    def test_chat_message_renderer_supports_markdown_tables_and_modifier_links(self):
        message_bubble = (
            PROJECT_ROOT / "src/app/chat-interface/components/MessageBubble.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("function renderMarkdownTable", message_bubble)
        self.assertIn("isMarkdownTableStart", message_bubble)
        self.assertIn("/generated", message_bubble)
        self.assertIn("window.open(url, '_blank'", message_bubble)

    def test_frontend_generated_route_serves_backend_artifacts(self):
        route = (PROJECT_ROOT / "src/app/generated/[...path]/route.ts").read_text(encoding="utf-8")

        self.assertIn("generated_artifacts", route)
        self.assertIn("application/pdf", route)
        self.assertIn("application/vnd.openxmlformats-officedocument.presentationml.presentation", route)
        self.assertIn("path.relative", route)
        self.assertIn("Generated file not found", route)

    def test_yesterday_ipl_search_query_uses_requested_temporal_word(self):
        query = _build_live_search_query("yesterday IPL match teams and highest score")

        self.assertIn("IPL", query)
        self.assertIn("highest scorer", query)
        self.assertIn("match teams score", query)

    def test_openai_latest_model_query_prefers_official_source(self):
        query = _build_live_search_query("what is the latest GPT model today")

        self.assertIn("site:openai.com", query)
        self.assertIn("official", query)

    def test_live_silver_price_query_prefers_bullion_and_exchange_sources(self):
        query = _build_live_search_query("what is current silver price in India today")
        profile = _preferred_live_source_profile("what is current silver price in India today")

        self.assertIn("site:ebullion.in", query)
        self.assertIn("site:ibjarates.com", query)
        self.assertIn("site:mcxindia.com", query)
        self.assertIn("eBullion", profile["policy"])
        self.assertIn("unit", profile["policy"])

    def test_live_per_gram_metal_query_prefers_ebullion_even_without_price_word(self):
        query = _build_live_search_query("silver and gold per gram")

        self.assertIn("site:ebullion.in", query)
        self.assertIn("silver gold rate", query)

    @patch(
        "backend.ai_engine._read_url",
        return_value='{"data":{"gold":{"sellRate":16216.25,"buyRate":15511.6,"variationType":"up","variation":"132.45"},"silver":{"sellRate":290.92,"buyRate":272.7,"variationType":"up","variation":"3.21"}}}',
    )
    def test_direct_metal_context_uses_ebullion_per_gram_first(self, _mock_read):
        context = _build_direct_live_data_context("silver and gold per gram")

        self.assertIn("eBullion live metal ticker", context)
        self.assertIn("Silver sell INR 290.92/g", context)
        self.assertIn("Gold sell INR 16216.25/g", context)

    def test_live_weather_query_prefers_imd_sources(self):
        query = _build_live_search_query("current weather in Hyderabad today")

        self.assertIn("site:mausam.imd.gov.in", query)
        self.assertIn("official IMD", query)

    def test_live_stock_query_prefers_exchange_sources(self):
        query = _build_live_search_query("current TCS stock price")

        self.assertIn("site:nseindia.com", query)
        self.assertIn("site:bseindia.com", query)

    def test_live_india_news_query_avoids_generic_search_noise(self):
        query = _build_live_search_query("what happened in India latest news today")

        self.assertIn("site:thehindu.com", query)
        self.assertIn("site:indianexpress.com", query)
        self.assertIn("India latest news today", query)

    @patch(
        "backend.ai_engine._read_url",
        return_value=(
            "<?xml version='1.0'?><rss><channel><item>"
            "<title>Verified headline from source</title><link>https://example.com/one</link>"
            "<pubDate>Tue, 19 May 2026 16:30:00 +0530</pubDate>"
            "<description>Source-reported description.</description></item></channel></rss>"
        ),
    )
    def test_news_context_forbids_extra_confident_claims(self, _mock_read):
        context = _fetch_news_direct_context("latest India news today")

        self.assertIn("source-attributed headlines", context)
        self.assertIn("Do not create extra news claims", context)
        self.assertIn("Source-reported", context)

    @patch("backend.ai_engine._read_url")
    def test_direct_news_context_uses_rss_before_generic_search(self, mock_read):
        mock_read.return_value = (
            "<?xml version='1.0'?><rss><channel><item>"
            "<title>India headline one</title><link>https://example.com/one</link>"
            "<pubDate>Thu, 14 May 2026 01:00:00 +0530</pubDate>"
            "<description>Verified current item.</description></item></channel></rss>"
        )

        context = _build_direct_live_data_context("what happened in India latest news today")

        self.assertIn("India current news RSS/news feeds", context)
        self.assertIn("India headline one", context)

    def test_live_question_split_handles_compound_query(self):
        questions = _split_live_questions(
            "yesterday IPL match what are the teams and who won the match and what is the highest score"
        )

        self.assertGreaterEqual(len(questions), 2)
        self.assertTrue(any("who won" in question for question in questions))

    def test_live_ipl_context_builds_direct_answer_hint(self):
        live_context = (
            "LIVE WEB CONTEXT:\n"
            "1. Aaj Kiska Match Hai IPL Today Match Schedule 13 May 2026 RCB vs KKR\n"
            "   URL: https://www.timesnowhindi.com/sports/cricket/example\n"
            "2. Royal Challengers Bengaluru vs Kolkata Knight Riders full schedule\n"
            "   URL: https://newsable.asianetnews.com/example"
        )

        self.assertEqual(
            _extract_matchups_from_live_context(live_context)[0],
            "Royal Challengers Bengaluru (RCB) vs Kolkata Knight Riders (KKR)",
        )

        hint = _build_live_answer_hint("what are the teams having an IPL match today", live_context)

        self.assertIn("Royal Challengers Bengaluru (RCB) vs Kolkata Knight Riders (KKR)", hint)
        self.assertIn("Do not tell the user to check a website", hint)
        self.assertIn("IST", hint)

    def test_live_matchup_extraction_understands_face_wording(self):
        live_context = "Page details: Royal Challengers Bengaluru face Kolkata Knight Riders at Raipur."

        self.assertEqual(
            _extract_matchups_from_live_context(live_context),
            ["Royal Challengers Bengaluru vs Kolkata Knight Riders"],
        )

    def test_live_matchup_extraction_filters_non_ipl_noise(self):
        live_context = (
            "Page details: Royal Challengers Bengaluru face Kolkata Knight Riders. "
            "Unrelated card: Roman Reigns vs Jacob Fatu."
        )

        self.assertEqual(
            _extract_matchups_from_live_context(live_context),
            ["Royal Challengers Bengaluru vs Kolkata Knight Riders"],
        )

    @patch("backend.ai_engine._fetch_live_web_context", return_value="LIVE WEB CONTEXT:\n1. verified result")
    def test_multi_question_live_context_keeps_each_question(self, _mock_fetch):
        context = _build_multi_question_live_context(
            "what is the latest GPT model and what is today's IPL match score"
        )

        self.assertIn("LIVE QUESTION 1", context)
        self.assertIn("LIVE QUESTION 2", context)
        self.assertIn("SEARCH QUERY:", context)

    @patch("backend.ai_engine._fetch_live_web_context", return_value="LIVE WEB CONTEXT:\n1. verified result")
    def test_multi_question_live_context_inherits_ipl_and_date(self, _mock_fetch):
        context = _build_multi_question_live_context(
            "yesterday IPL match what are the teams and who won the match and what is the highest score"
        )

        self.assertIn("LIVE QUESTION 1", context)
        self.assertIn("LIVE QUESTION 2: yesterday who won the match IPL", context)
        self.assertIn("LIVE QUESTION 3: yesterday what is the highest score IPL", context)

    def test_auth_password_hash_verification(self):
        hashed = hash_password("correct-password")

        self.assertTrue(verify_password("correct-password", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))
        self.assertNotIn("correct-password", hashed)

    def test_auth_email_normalization(self):
        self.assertEqual(normalize_auth_email("  USER@Example.COM "), "user@example.com")


if __name__ == "__main__":
    unittest.main()
