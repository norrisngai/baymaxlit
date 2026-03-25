"""HKDSE English Language subject knowledge."""

ENGLISH_KNOWLEDGE = {
    "test_modes": ["reading", "writing"],
    "style_guide": (
        "Follow the HKDSE English Language exam style.\n"
        "PAPER 1 (Reading):\n"
        "- Part A: easier reading comprehension with short passages (~300 words)\n"
        "- Part B1: moderate comprehension (for students aiming at Level 3–4)\n"
        "- Part B2: harder comprehension (for students aiming at Level 4–5**)\n"
        "Question types include: MC, fill-in-the-blank, short answer, matching,\n"
        "  true/false/not given, summary cloze, and longer written responses.\n"
        "The passage topics should be realistic: news, letters, articles, ads,\n"
        "  stories, informational texts.\n\n"
        "For junior forms (F1-F3), use simpler passages (~200 words), more MC,\n"
        "  fill-in-the-blanks, and basic comprehension questions."
    ),
    "reading_exemplar_stems": [
        "Read the following passage and answer questions 1-5.\n"
        "[A short passage about a topic relevant to HK students]\n"
        "1. According to the passage, what is the main reason...?\n"
        "2. The word '___' in line X most likely means...\n"
        "3. True, False, or Not Given: ...\n"
        "4. Complete the summary below using words from the passage.\n"
        "5. In your own words, explain why...",

        "Read the following email and answer the questions.\n"
        "[An email about a school event / community activity]\n"
        "1. (MC) What is the purpose of this email?\n"
        "2. (Short answer) When should students submit their forms?",
    ],
    "writing_prompts_by_form": {
        "junior": [
            "Write an email to your friend describing a recent school trip. (About 120 words)",
            "Your school magazine is looking for articles about 'My Favourite Hobby'. Write an article. (About 150 words)",
            "Write a letter to your pen pal telling them about life in Hong Kong. (About 120 words)",
        ],
        "senior": [
            "You are the chairperson of the Student Union. Write a speech to persuade students to participate in a charity event. (About 400 words)",
            "Write a blog post discussing whether social media has a positive or negative impact on teenagers. (About 350 words)",
            "Your school magazine is publishing a special issue on 'Work-Life Balance'. Write an article giving advice to senior secondary students. (About 400 words)",
            "Write a letter to the editor of a local newspaper expressing your views on reducing plastic waste in Hong Kong. (About 400 words)",
        ],
    },
    "marking_notes": {
        "reading": (
            "MC: 1 mark each. Short answer: 1-2 marks. "
            "Longer responses: up to 4 marks depending on depth. "
            "Accept answers that show understanding even if not perfectly worded."
        ),
    },
    "question_type_mix": {
        "reading": {"mcq": 0.35, "true_false": 0.15, "short_answer": 0.50},
    },
}
