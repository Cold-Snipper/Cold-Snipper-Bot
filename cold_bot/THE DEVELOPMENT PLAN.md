# The Development Plan (110 Steps)

Project Setup Phase (Steps 1-10)

1. Create Project Structure: Prompt: "Create a new Python project folder named 'cold_bot' with subfolders: silos (for individual modules), prompts (for LLM templates), tests (for pytest files). Add a requirements.txt with: playwright, playwright-stealth, ollama, pyyaml, sqlite3, yagmail, pytest, beautifulsoup4, lxml. Include a .gitignore for __pycache__ and .env."

2. Install Dependencies: Prompt: "Generate a bash script install_deps.sh to pip install from requirements.txt and run 'playwright install' for browsers. Assume virtualenv is active."

3. Set Up Git: Prompt: "Create a git init command and initial commit message for the cold_bot project. Add a README.md with project overview: 'Automated real estate outreach bot using Playwright, Ollama, and silos architecture'."

4. Create Config YAML Template: Prompt: "Generate a sample config.yaml file with keys: start_urls (list), criteria (str), ollama_model (str), email (dict with from, app_password, smtp_host), limits (dict with max_contacts_per_hour, scroll_depth, delay_min, delay_max), selectors (dict with listing), database (str). Place in root."

5. Environment Setup: Prompt: "Write a .env.example file for sensitive vars like EMAIL_FROM, EMAIL_PW. Include instructions to copy to .env and load via dotenv if needed."

6. Global Utils File: Prompt: "Create utils.py in root with helper functions: rotate_ua() returning random user-agent from a list of 10 real ones (desktop and mobile), and random_delay(min_sec, max_sec) using time.sleep(random.randint)."

7. Prompts Folder Setup: Prompt: "In prompts/ folder, create eligibility.txt with template: 'You are a real estate qualifier. Text: """{text}""" Criteria: {criteria} Output JSON: {"eligible": true/false, "reason": "brief", "summary": "desc"}'."

8. Add Contact Prompt: Prompt: "In prompts/, add extract_contact.txt: 'Extract email/phone from: """{text}""" JSON: {"email": "str or null", "phone": "str or null"}'."

9. Add Proposal Prompt: Prompt: "In prompts/, add generate_proposal.txt: 'Write short polite email (150-220 words) proposing real estate partnership. From: {from} To: Owner of {summary} Key points: Compliment, offer help, no fees, CTA. Subject first, then body.'."

10. Docstring Template: Prompt: "Create a template.py with example docstring for functions: '''Description. Args: arg1 (type): desc. Returns: type: desc. Raises: exc: when.''' Use this in all future code."

11. Create File: Prompt: "In silos/, create config_loader.py with empty class ConfigLoader."

12. Add Load Method: Prompt: "In config_loader.py, add method load_config(file_path: str) -> dict using yaml.safe_load. Handle FileNotFoundError."

13. Add Validation: Prompt: "In config_loader.py, add validate_config(config: dict) -> None that checks required keys like 'start_urls', raises ValueError on missing."

14. Integrate Validation: Prompt: "Update load_config in config_loader.py to call validate_config after loading."

15. Add Defaults: Prompt: "In validate_config, set defaults if missing: e.g., limits['delay_min'] = 5."

16. Docstrings: Prompt: "Add docstrings to all functions in config_loader.py using the template from Step 10."

17. Unit Test File: Prompt: "In tests/, create test_config_loader.py with pytest import."

18. Unit Test Load: Prompt: "In test_config_loader.py, add test_load_success: create temp yaml, assert loads correctly."

19. Unit Test Validation: Prompt: "In test_config_loader.py, add test_validate_missing_key: assert raises ValueError on incomplete config."

20. Run Tests: Prompt: "Generate a pytest command for test_config_loader.py; assume success means silo ready."

21. Create File: Prompt: "In silos/, create browser_automation.py importing playwright.sync_api, playwright_stealth, random, from utils import rotate_ua, random_delay."

22. Add Init Function: Prompt: "In browser_automation.py, add init_browser(headless: bool = True) -> tuple: launch chromium, new_context with viewport 1280x800, user_agent from rotate_ua, apply stealth_sync."

23. Add Proxy Support: Prompt: "Update init_browser to accept proxy: dict optional from config, add to context if present."

24. Add Scroll Function: Prompt: "Add scroll_and_navigate(page, url: str, depth: int, min_delay: int, max_delay: int): goto url, for _ in range(depth): evaluate scrollTo bottom, wait_for_timeout with random_delay."

25. Humanize Scroll: Prompt: "Enhance scroll_and_navigate: add page.mouse.move(random x/y) before each scroll for anti-detection."

26. Error Handling: Prompt: "In init_browser and scroll, catch PlaywrightError, log and retry once."

27. Close Method: Prompt: "Add close_browser(browser, context): close them gracefully."

28. Docstrings: Prompt: "Add docstrings to all in browser_automation.py."

29. Unit Test File: Prompt: "Create test_browser_automation.py in tests/."

30. Mock Init Test: Prompt: "In tests, add mock test_init_browser: patch launch, assert context user_agent changes."

31. Functional Test Setup: Prompt: "Add test_scroll: non-headless, goto google.com, scroll 5 times, save screenshot."

32. Test Proxy: Prompt: "Add test with dummy proxy, assert set in context."

33. Test Delays: Prompt: "Mock time.sleep, assert called with range in scroll."

34. Test Errors: Prompt: "Simulate error in goto, assert retry."

35. Run Tests: Prompt: "Pytest command for test_browser_automation.py."

36. Create File: Prompt: "In silos/, create data_scraper.py importing beautifulsoup4, lxml."

37. Add Extract Function: Prompt: "Add extract_listings(page, selector: str) -> list[dict]: query_selector_all, for each: {'text': inner_text(), 'hash': hash(text)}."

38. Fallback Parsing: Prompt: "If selector fails, fallback to BeautifulSoup(page.content(), 'lxml') for broader extraction."

39. Deduplicate: Prompt: "In extract_listings, use set for hashes to skip duplicates."

40. Site-Specific: Prompt: "Add param site: str, adjust selector if site=='facebook' vs 'craigslist'."

41. Error Handling: Prompt: "Catch TimeoutError, return partial list."

42. Docstrings: Prompt: "Docstrings for all."

43. Unit Test File: Prompt: "test_data_scraper.py."

44. Unit Extract: Prompt: "Mock page with HTML, assert extracts 3 listings."

45. Test Dedup: Prompt: "Feed duplicates, assert unique output."

46. Functional Test: Prompt: "Integrate with mock page from Silo 2, extract from test URL."

47. Test Fallback: Prompt: "Simulate selector fail, assert BS used."

48. Run Tests: Prompt: "Pytest for scraper."

49. Create File: Prompt: "silos/llm_integration.py importing ollama, json, os for prompts/."

50. Load Prompts: Prompt: "Add load_prompt(file: str) -> str: read from prompts/."

51. Classify Function: Prompt: "classify_eligible(text: str, criteria: str, model: str): load eligibility.txt, format prompt, ollama.chat format='json', parse return dict."

52. Extract Contact: Prompt: "Similar for extract_contact(text, model): use extract_contact.txt."

53. Generate Proposal: Prompt: "generate_proposal(summary: str, contact: str, model: str, from_email: str): format proposal.txt with from_email."

54. Hallucination Retry: Prompt: "In all, if json.loads fails, retry once with 'Strict JSON only' appended to prompt."

55. Model Fallback: Prompt: "If model not found, default to 'llama3'."

56. Docstrings: Prompt: "All functions."

57. Unit Test File: Prompt: "test_llm_integration.py."

58. Mock Classify: Prompt: "Patch ollama.chat with fake JSON, assert eligible bool."

59. Test Extract: Prompt: "Feed text with email, assert extracts."

60. Test Proposal: Prompt: "Assert output starts with 'Subject:'."

61. Test Retry: Prompt: "Simulate bad JSON, assert retries."

62. Functional Test: Prompt: "Require Ollama running, test with sample text."

63. Run Tests: Prompt: "Pytest, skip functional if no Ollama."

64. Create File: Prompt: "silos/email_sender.py importing yagmail, sqlite3."

65. DB Init: Prompt: "init_db(db_path: str): create table contacts (contact str PRIMARY KEY, status str, timestamp datetime)."

66. Is Contacted: Prompt: "is_contacted(db_path, contact: str) -> bool: query exists."

67. Log Contact: Prompt: "log_contact(db_path, contact, status): insert or update."

68. Send Email: Prompt: "send_email(to: str, proposal: str, from_email: str, app_pw: str, smtp_host: str) -> bool: yagmail.SMTP, send, catch exceptions."

69. Rate Limit Check: Prompt: "Add check_recent_sends(db_path, max_per_hour: int) -> bool before send."

70. Docstrings: Prompt: "All."

71. Unit Test File: Prompt: "test_email_sender.py."

72. Test DB Init: Prompt: "Temp db, assert table created."

73. Test Is Contacted: Prompt: "Insert, assert True."

74. Mock Send: Prompt: "Patch yagmail, assert called with params."

75. Test Rate Limit: Prompt: "Insert recent logs, assert blocks if over."

76. Functional Test: Prompt: "Use mailtrap for mock send."

77. Run Tests: Prompt: "Pytest."

78. Create File: Prompt: "root main.py importing all silos/*."

79. Main Function: Prompt: "def main(config_path: str): config = ConfigLoader.load_config(config_path)"

80. Browser Setup: Prompt: "In main: browser, context, page = init_browser(config['headless'])"

81. Loop Structure: Prompt: "While True: for url in start_urls: scroll_and_navigate(page, url, config['limits']['scroll_depth'], ... )"

82. Extract and Process: Prompt: "listings = extract_listings(page, config['selectors']['listing']); for lst: if classify_eligible(lst['text'], criteria, model)['eligible']"

83. Contact and Send: Prompt: "contact = extract_contact(...); if contact and not is_contacted(...): proposal = generate_proposal(...); if send_email(...): log_contact('success')"

84. Cooldown: Prompt: "After loop: random_delay(config['limits']['cooldown_min'], max)"

85. Signal Handling: Prompt: "Import signal; add handler for SIGINT to close_browser gracefully."

86. CLI Args: Prompt: "Use argparse for --config default 'config.yaml'."

87. Docstrings: Prompt: "For main."

88. Integration Test File: Prompt: "tests/test_main.py with mocks for all silos."

89. E2E Test: Prompt: "Mock full run: assert loop calls each silo."

90. Run Tests: Prompt: "Pytest all."

91. Merge Branches: Prompt: "Git commands to merge silo branches to main."

92. Full Run Script: Prompt: "Update main.py for headless=True default."

93. Error Propagation: Prompt: "In main, wrap loop in try-except, log errors."

94. Logging Setup: Prompt: "Add logging.basicConfig to file 'bot.log'."

95. Proxy Rotation: Prompt: "If config has proxies list, rotate in init_browser."

96. Multi-Site Support: Prompt: "In scraper, add if-elif for different sites' selectors."

97. LLM Prompt Refinement: Prompt: "Test and update prompts.txt for better accuracy."

98. Performance Metrics: Prompt: "Add timing to loop, log avg per listing."

99. Ethical Flag: Prompt: "Add config['manual_approve']: if True, print proposal and wait input before send."

100. Dockerfile: Prompt: "Create Dockerfile for containerization: from python:3.12, copy project, install deps, entrypoint main.py."

101. CI Script: Prompt: "GitHub Actions yaml for pytest on push."

102. Refactor Duplicates: Prompt: "Scan all code for repeated code, move to utils.py."

103. Type Hints: Prompt: "Add typing imports, hint all functions."

104. Linting: Prompt: "Add black and flake8 to requirements, generate lint.sh."

105. Security Scan: Prompt: "Check for hardcodes, ensure .env usage."

106. Documentation: Prompt: "Update README with usage: 'python main.py --config config.yaml'."

107. Benchmark: Prompt: "Test on sample FB URL, log 10 listings processed."

108. Edge Case Tests: Prompt: "Add tests for no listings, bad contacts."

109. Final Integration Test: Prompt: "E2E with all real (mock send), assert DB populated."

110. Deployment Notes: Prompt: "Add notes.md: Run Ollama server, set env, ethical use warning."
