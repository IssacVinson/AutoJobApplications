import os
import json
import time
import requests
import re  # Added to fix 'name 're' is not defined' error
import base64
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize Grok client
client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

# Function to download resume from GitHub
def download_resume(url, local_path):
    print(f"Attempting to download resume from {url} to {local_path}")
    response = requests.get(url)
    if response.status_code == 200:
        with open(local_path, "wb") as f:
            f.write(response.content)
        print(f"Success: Resume downloaded to {local_path}")
    else:
        print(f"Failure: Failed to download resume from {url}. Status code: {response.status_code}")
        raise Exception(f"Failed to download resume from {url}. Status code: {response.status_code}")

# Download resume
resume_url = "https://raw.githubusercontent.com/IssacVinson/AutoJobApplications/main/Resume%20Mar%2025.pdf"
local_resume_path = "/home/vinso/job_applier/resume.pdf"
download_resume(resume_url, local_resume_path)

# Load profile and update resume path
print("Attempting to load profile.json")
with open("profile.json", "r") as f:
    profile = json.load(f)
profile["resume"] = local_resume_path  # Update the resume path dynamically
print("Success: Profile loaded and resume path updated")

# Set up Selenium with headless Chromium
print("Attempting to set up Selenium WebDriver")
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
service = Service("/usr/bin/chromedriver")  # Correct path
driver = webdriver.Chrome(service=service, options=chrome_options)
print("Success: Selenium WebDriver set up")

# Function to take a screenshot and encode it as base64
def take_screenshot():
    print("Attempting to take screenshot")
    screenshot = driver.get_screenshot_as_base64()
    if screenshot:
        print("Success: Screenshot captured and encoded as base64")
    else:
        print("Failure: Failed to capture screenshot")
    return screenshot

# Function to scrape jobs using vision-based approach
def scrape_jobs_with_vision(url, source):
    print(f"Scraping {source} with vision-based approach: {url}")
    driver.get(url)
    time.sleep(5)  # Wait for page to load

    # Take screenshot
    screenshot = take_screenshot()
    if not screenshot:
        print(f"Failure: No screenshot available for {source}")
        return []

    # Ask Grok to identify job listings in the screenshot
    print(f"Attempting to analyze {source} screenshot with Grok")
    try:
        response = client.chat.completions.create(
            model="grok-beta",
            messages=[
                {
                    "role": "system",
                    "content": "You are a web automation assistant with vision capabilities. Analyze the provided screenshot of a job search page and identify job listings. For each job, provide: 1) The job title, 2) The clickable element (XPath) to access the job details or application page. Return a JSON object with a key 'jobs' containing a list of dictionaries, each with 'title' and 'xpath'. If no jobs are found, return: {'jobs': []}."
                },
                {
                    "role": "user",
                    "content": f"Analyze this screenshot to identify job listings: data:image/png;base64,{screenshot}"
                }
            ],
            timeout=30
        )
        print("Success: Grok API call completed")
        instructions = response.choices[0].message.content.strip()
        print(f"Grok response: {instructions}")
        json_match = re.search(r'\{.*\}', instructions, re.DOTALL)
        if json_match:
            instructions = json_match.group(0)
            print(f"Success: Extracted JSON: {instructions}")
        else:
            print("Failure: No JSON pattern found in Grok response")
            return []
        job_data = json.loads(instructions)
        if not isinstance(job_data, dict) or 'jobs' not in job_data:
            print(f"Failure: Invalid job data from Grok for {source}: {instructions}")
            return []

        job_list = []
        for i, job in enumerate(job_data.get("jobs", [])):
            title = job.get("title", f"Untitled_{i}")
            xpath = job.get("xpath")
            if not xpath:
                print(f"Warning: No XPath for job {i} from {source}")
                continue
            try:
                print(f"Attempting to find and click job {i} with XPath: {xpath}")
                element = driver.find_element(By.XPATH, xpath)
                link = element.get_attribute("href") or url
                print(f"Success: Found element, attempting to click")
                element.click()
                time.sleep(2)  # Wait for navigation
                current_url = driver.current_url
                job_list.append({"title": title, "link": current_url, "source": source})
                print(f"Success: Scraped job {i} from {source}: {title} at {current_url}")
                driver.get(url)  # Return to search page
                time.sleep(2)
            except Exception as e:
                print(f"Failure: Error navigating to job {i} from {source}: {e}")
                job_list.append({"title": title, "link": url, "source": source})
        print(f"Success: Found {len(job_list)} jobs from {source}")
        return job_list
    except Exception as e:
        print(f"Failure: Failed to scrape {source} jobs with vision: {e}")
        return []

def scrape_jobs_indeed(keyword, location):
    url = f"https://www.indeed.com/jobs?q={keyword}&l={location}&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11"
    return scrape_jobs_with_vision(url, "Indeed")

# Commenting out LinkedIn for now
# def scrape_jobs_linkedin(keyword, location):
#     keyword_formatted = keyword.replace(" OR ", "+").replace(" ", "+")
#     url = f"https://www.linkedin.com/jobs/search/?keywords={keyword_formatted}&location={location}&f_WT=2"
#     return scrape_jobs_with_vision(url, "LinkedIn")

def scrape_jobs_glassdoor(keyword, location):
    keyword_formatted = keyword.replace(" OR ", "+").replace(" ", "+")
    url = f"https://www.glassdoor.com/Job/{keyword_formatted}-jobs-SRCH_KO0,30.htm?remoteWorkType=1"
    return scrape_jobs_with_vision(url, "Glassdoor")

def scrape_jobs_x(keyword, location):
    query = f"{keyword} {location} job -filter:replies"
    query_formatted = query.replace(" ", "%20").replace("OR", "%20OR%20")
    url = f"https://x.com/search?q={query_formatted}&src=typed_query"
    print(f"Scraping X with vision-based approach: {url}")
    driver.get(url)
    time.sleep(5)  # Wait for page to load

    # Take screenshot
    screenshot = take_screenshot()
    if not screenshot:
        print(f"Failure: No screenshot available for X")
        return []

    # Ask Grok to identify job postings
    print(f"Attempting to analyze X screenshot with Grok")
    try:
        response = client.chat.completions.create(
            model="grok-beta",
            messages=[
                {
                    "role": "system",
                    "content": "You are a web automation assistant with vision capabilities. Analyze the provided screenshot of an X search page and identify job postings. For each job, provide: 1) The job title (or first 50 characters of the tweet), 2) The clickable element (XPath) to access the job link. Return a JSON object with a key 'jobs' containing a list of dictionaries, each with 'title' and 'xpath'. If no jobs are found, return: {'jobs': []}."
                },
                {
                    "role": "user",
                    "content": f"Analyze this screenshot to identify job postings: data:image/png;base64,{screenshot}"
                }
            ],
            timeout=30
        )
        print("Success: Grok API call completed for X")
        instructions = response.choices[0].message.content.strip()
        print(f"Grok response for X: {instructions}")
        json_match = re.search(r'\{.*\}', instructions, re.DOTALL)
        if json_match:
            instructions = json_match.group(0)
            print(f"Success: Extracted JSON for X: {instructions}")
        else:
            print("Failure: No JSON pattern found in X Grok response")
            return []
        job_data = json.loads(instructions)
        if not isinstance(job_data, dict) or 'jobs' not in job_data:
            print(f"Failure: Invalid job data from Grok for X: {instructions}")
            return []

        job_list = []
        for i, job in enumerate(job_data.get("jobs", [])):
            title = job.get("title", f"Untitled_{i}")
            xpath = job.get("xpath")
            if not xpath:
                print(f"Warning: No XPath for X job {i}")
                continue
            try:
                print(f"Attempting to find X job {i} with XPath: {xpath}")
                element = driver.find_element(By.XPATH, xpath)
                link = element.get_attribute("href") or url
                job_list.append({"title": title, "link": link, "source": "X"})
                print(f"Success: Scraped job {i} from X: {title} at {link}")
            except Exception as e:
                print(f"Failure: Error scraping X job {i}: {e}")
                job_list.append({"title": title, "link": url, "source": "X"})
        print(f"Success: Found {len(job_list)} jobs from X")
        return job_list
    except Exception as e:
        print(f"Failure: Failed to scrape X jobs with vision: {e}")
        return []

def filter_job(job_link):
    print(f"Attempting to filter job: {job_link}")
    driver.get(job_link)
    time.sleep(2)
    # Take screenshot
    screenshot = take_screenshot()
    if not screenshot:
        print(f"Failure: No screenshot available for filtering {job_link}")
        return False

    # Ask Grok to extract job description from screenshot
    print(f"Attempting to extract job description with Grok for {job_link}")
    try:
        response = client.chat.completions.create(
            model="grok-beta",
            messages=[
                {
                    "role": "system",
                    "content": "You are a job application assistant with vision capabilities. Analyze the provided screenshot of a job posting page and extract the job description text. Return the text as a string. If no description is found, return: 'No description found.'"
                },
                {
                    "role": "user",
                    "content": f"Extract the job description from this screenshot: data:image/png;base64,{screenshot}"
                }
            ]
        )
        print("Success: Grok API call completed for job description")
        job_desc = response.choices[0].message.content.strip()
        print(f"Extracted job description: {job_desc}")
        if not job_desc:
            job_desc = "No description found."
    except Exception as e:
        print(f"Failure: Failed to extract job description with vision: {e}")
        job_desc = "No description found."

    with open("debug_job_desc.txt", "a") as f:
        f.write(f"Link: {job_link}\nDescription: {job_desc}\n\n")
    response = client.chat.completions.create(
        model="grok-beta",
        messages=[
            {"role": "system", "content": "You are a job application assistant."},
            {"role": "user", "content": f"Given this profile: {profile}, does this job description match my skills and experience? Job description: {job_desc}"}
        ]
    )
    answer = response.choices[0].message.content.lower()
    print(f"Filter decision: {'yes' if 'yes' in answer or 'match' in answer else 'no'}")
    return "yes" in answer or "match" in answer

def generate_cover_letter(job_desc):
    print(f"Attempting to generate cover letter for description: {job_desc[:50]}...")
    response = client.chat.completions.create(
        model="grok-beta",
        messages=[
            {"role": "system", "content": "You are a job application assistant."},
            {"role": "user", "content": f"Using this profile: {profile}, write a cover letter for this job description: {job_desc}"}
        ]
    )
    cover_letter = response.choices[0].message.content
    print("Success: Cover letter generated")
    return cover_letter

def answer_essay_question(question):
    print(f"Attempting to answer essay question: {question}")
    sensitive_keywords = ["ssn", "social security", "password", "credit card", "bank account"]
    if any(keyword in question.lower() for keyword in sensitive_keywords):
        print(f"Sensitive question detected: {question}")
        user_answer = input("Please provide an answer (or press Enter to skip): ")
        return user_answer if user_answer else "Skipped by user"
    
    try:
        response = client.chat.completions.create(
            model="grok-beta",
            messages=[
                {"role": "system", "content": "You are a job application assistant answering essay questions based on this profile: " + str(profile)},
                {"role": "user", "content": f"Answer this question: {question}"}
            ]
        )
        answer = response.choices[0].message.content
        print(f"Success: Generated answer for {question}")
        return answer
    except Exception as e:
        print(f"Failure: Failed to generate answer for {question}: {e}")
        user_answer = input("Please provide an answer (or press Enter to skip): ")
        return user_answer if user_answer else "Skipped by user"

def apply_to_job(job_link):
    print(f"Applying to: {job_link}")
    driver.get(job_link)
    time.sleep(5)  # Initial wait for page load

    # Generate cover letter
    try:
        job_desc = driver.find_element(By.CLASS_NAME, "jobsearch-JobDescriptionSection").text
    except:
        job_desc = "No description found."
    cover_letter = generate_cover_letter(job_desc)
    with open("cover_letter.txt", "w") as f:
        f.write(cover_letter)

    # Vision-based application loop
    max_steps = 10  # Maximum steps to avoid infinite loops
    success = False
    for step in range(max_steps):
        print(f"Step {step + 1}/{max_steps} of application process")
        # Take screenshot
        screenshot = take_screenshot()
        if not screenshot:
            print(f"Failure: No screenshot available at step {step}")
            break

        # Ask Grok for the next action
        print(f"Attempting to determine next action with Grok at step {step}")
        try:
            response = client.chat.completions.create(
                model="grok-beta",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a web automation assistant with vision capabilities. Analyze the provided screenshot of a job application page and determine the next action to proceed with the application. Identify: 1) Input fields to fill (e.g., name, email, phone) with their XPaths and the type (e.g., 'text', 'checkbox'), 2) File upload fields for resume or cover letter with their XPaths, 3) The next button to click (e.g., 'Apply', 'Next', 'Submit') with its XPath. Return a JSON object with keys 'inputs', 'file_inputs', and 'button', where 'inputs' and 'file_inputs' are lists of dictionaries with 'xpath' and 'type', and 'button' is a dictionary with 'xpath' and 'text'. If no actions are found or the application is complete, return: {'inputs': [], 'file_inputs': [], 'button': null, 'complete': true/false}."
                    },
                    {
                        "role": "user",
                        "content": f"Determine the next action for this job application: data:image/png;base64,{screenshot}"
                    }
                ],
                timeout=30
            )
            print("Success: Grok API call completed for action determination")
            instructions = response.choices[0].message.content.strip()
            print(f"Grok action response: {instructions}")
            json_match = re.search(r'\{.*\}', instructions, re.DOTALL)
            if json_match:
                instructions = json_match.group(0)
                print(f"Success: Extracted action JSON: {instructions}")
            else:
                print("Failure: No JSON pattern found in Grok action response")
                break
            action_plan = json.loads(instructions)
            if not isinstance(action_plan, dict) or not all(key in action_plan for key in ['inputs', 'file_inputs', 'button']):
                print(f"Failure: Invalid action plan from Grok: {instructions}")
                break

            # Check if application is complete
            if action_plan.get("complete", False):
                print("Success: Application process completed according to Grok!")
                success = True
                break

            # Fill input fields
            for input_field in action_plan.get("inputs", []):
                xpath = input_field.get("xpath", "")
                field_type = input_field.get("type", "text")
                if not xpath:
                    print(f"Warning: No XPath for input at step {step}")
                    continue
                try:
                    print(f"Attempting to fill {field_type} field with xpath: {xpath}")
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    if field_type == "text":
                        if "first_name" in xpath.lower():
                            element.send_keys(profile["name"].split()[0])
                        elif "last_name" in xpath.lower():
                            element.send_keys(profile["name"].split()[-1])
                        elif "email" in xpath.lower():
                            element.send_keys(profile["email"])
                        elif "phone" in xpath.lower():
                            element.send_keys(profile["phone"])
                        else:
                            answer = answer_essay_question(f"Fill this field: {xpath}")
                            element.send_keys(answer if answer else "")
                    elif field_type in ["checkbox", "radio"]:
                        element.click()
                    print(f"Success: Filled {field_type} field with xpath: {xpath}")
                except Exception as e:
                    print(f"Failure: Failed to fill input {xpath}: {e}")

            # Upload files
            for file_input in action_plan.get("file_inputs", []):
                xpath = file_input.get("xpath", "")
                if not xpath:
                    print(f"Warning: No XPath for file input at step {step}")
                    continue
                try:
                    print(f"Attempting to upload file with xpath: {xpath}")
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    if "resume" in xpath.lower():
                        element.send_keys(profile["resume"])
                    elif "cover" in xpath.lower():
                        element.send_keys(os.path.abspath("cover_letter.txt"))
                    print(f"Success: Uploaded file for xpath: {xpath}")
                except Exception as e:
                    print(f"Failure: Failed to upload file for {xpath}: {e}")

            # Click the next button
            button = action_plan.get("button")
            if button and button.get("xpath"):
                xpath = button["xpath"]
                max_retries = 2
                for attempt in range(max_retries):
                    try:
                        print(f"Attempt {attempt + 1}/{max_retries} to click button with xpath: {xpath}")
                        element = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        element.click()
                        time.sleep(2)
                        print(f"Success: Clicked button with xpath: {xpath} (text: {button.get('text', 'unknown')})")
                        break
                    except Exception as e:
                        print(f"Failure: Attempt {attempt + 1}/{max_retries} failed to click {xpath}: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                        else:
                            print(f"Failure: Max retries reached for button {xpath}")
                            break
            else:
                print("Warning: No button to click at step {step}, checking if application is complete...")
                break

        except Exception as e:
            print(f"Failure: Failed to determine next action with vision at step {step}: {e}")
            break

    # Verify application success
    if success:
        print("Attempting to verify application success with vision")
        # Take a final screenshot for verification
        screenshot = take_screenshot()
        if not screenshot:
            print("Failure: No screenshot available for verification")
        else:
            try:
                response = client.chat.completions.create(
                    model="grok-beta",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a web automation assistant with vision capabilities. Analyze the provided screenshot of a job application page and determine if the application has been successfully submitted. Look for phrases like 'Application submitted', 'Thank you', or 'applied'. Return a JSON object with a key 'success' (boolean) and 'message' (string) describing the confirmation."
                        },
                        {
                            "role": "user",
                            "content": f"Check if the application is successfully submitted: data:image/png;base64,{screenshot}"
                        }
                    ]
                )
                print("Success: Grok API call completed for verification")
                instructions = response.choices[0].message.content.strip()
                print(f"Verification response: {instructions}")
                json_match = re.search(r'\{.*\}', instructions, re.DOTALL)
                if json_match:
                    instructions = json_match.group(0)
                    print(f"Extracted verification JSON: {instructions}")
                else:
                    print("Failure: No JSON pattern found in verification response")
                verification = json.loads(instructions)
                if verification.get("success", False):
                    print(f"Success: Application successfully submitted (confirmed by vision): {verification.get('message', 'No message')}")
                else:
                    print(f"Warning: Application may have been submitted, but no confirmation found: {verification.get('message', 'No message')}")
            except Exception as e:
                print(f"Failure: Failed to verify application success with vision: {e}")
                print("Warning: Application may have been submitted, but verification failed.")
    else:
        print("Failure: Application process failed or did not complete.")

def main():
    # Scrape jobs from multiple sources
    keyword = "software developer"
    location = "remote"
    
    print("Scraping jobs from Indeed...")
    indeed_jobs = scrape_jobs_indeed(keyword, location)
    # Commenting out LinkedIn for now
    # print("Scraping jobs from LinkedIn...")
    # linkedin_jobs = scrape_jobs_linkedin(keyword, location)
    print("Scraping jobs from Glassdoor...")
    glassdoor_jobs = scrape_jobs_glassdoor(keyword, location)
    print("Scraping jobs from X...")
    x_jobs = scrape_jobs_x(keyword, location)

    # Combine all jobs
    jobs = indeed_jobs + [] + glassdoor_jobs + x_jobs  # Empty list replaces linkedin_jobs
    print(f"Found {len(jobs)} jobs in total.")

    # Limit to 10 jobs for testing
    jobs = jobs[:2]

    # Filter jobs
    filtered_jobs = []
    for job in jobs:
        if filter_job(job["link"]):
            filtered_jobs.append(job)
            print(f"Success: Job matches: {job['title']} (Source: {job['source']})")
        else:
            print(f"Failure: Job does not match: {job['title']} (Source: {job['source']})")
        time.sleep(2)  # Avoid overwhelming servers

    # Apply to first 3 filtered jobs
    for job in filtered_jobs[:3]:
        print(f"Starting application process for: {job['link']}")
        apply_to_job(job["link"])
        time.sleep(5)  # Avoid overwhelming servers

    driver.quit()
    print("Success: Driver quit")

if __name__ == "__main__":
    main()
