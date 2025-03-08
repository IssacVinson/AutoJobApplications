import os
import json
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize Grok client
client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

# Load profile
with open("profile.json", "r") as f:
    profile = json.load(f)

# Set up Selenium with headless Chromium
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
service = Service("/usr/lib/chromium-browser/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)

def scrape_jobs(keyword, location):
    url = f"https://www.indeed.com/jobs?q={keyword}&l={location}&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = soup.find_all("div", class_="job_seen_beacon")  # Updated class for Indeed
    
    job_list = []
    for job in jobs:
        title_elem = job.find("a", class_="jcs-JobTitle")
        if not title_elem:
            continue
        title = title_elem.text.strip()
        link = "https://www.indeed.com" + title_elem["href"]
        job_list.append({"title": title, "link": link})
    return job_list

def generate_cover_letter(job_desc):
    response = client.chat.completions.create(
        model="grok-beta",
        messages=[
            {"role": "system", "content": "You are a job application assistant."},
            {"role": "user", "content": f"Using this profile: {profile}, write a cover letter for this job description: {job_desc}"}
        ]
    )
    return response.choices[0].message.content

def answer_essay_question(question):
    response = client.chat.completions.create(
        model="grok-beta",
        messages=[
            {"role": "system", "content": "You are a job application assistant answering essay questions based on this profile: " + str(profile)},
            {"role": "user", "content": f"Answer this question: {question}"}
        ]
    )
    return response.choices[0].message.content

def apply_to_job(job_link):
    print(f"Applying to: {job_link}")
    driver.get(job_link)
    time.sleep(3)  # Wait for page to load

    # Get job description
    try:
        job_desc = driver.find_element(By.CLASS_NAME, "jobsearch-JobDescriptionSection").text
    except:
        job_desc = "No description found."

    # Generate cover letter
    cover_letter = generate_cover_letter(job_desc)
    with open("cover_letter.txt", "w") as f:
        f.write(cover_letter)

    # Click "Apply Now" button (adjust selector based on site)
    try:
        apply_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Apply Now')]")
        apply_button.click()
        time.sleep(2)
    except:
        print("Could not find Apply Now button.")
        return

    # Fill basic info
    try:
        driver.find_element(By.NAME, "first_name").send_keys(profile["name"].split()[0])
        driver.find_element(By.NAME, "last_name").send_keys(profile["name"].split()[-1])
        driver.find_element(By.NAME, "email").send_keys(profile["email"])
        driver.find_element(By.NAME, "phone").send_keys(profile["phone"])
    except:
        print("Could not fill basic info.")

    # Upload resume
    try:
        resume_field = driver.find_element(By.XPATH, "//input[@type='file'][contains(@id, 'resume')]")
        resume_field.send_keys(profile["resume"])
    except:
        print("Could not upload resume.")

    # Upload cover letter
    try:
        cover_letter_field = driver.find_element(By.XPATH, "//input[@type='file'][contains(@id, 'cover')]")
        cover_letter_field.send_keys(os.path.abspath("cover_letter.txt"))
    except:
        print("Could not upload cover letter.")

    # Answer essay questions (if any)
    try:
        questions = driver.find_elements(By.XPATH, "//textarea")
        for q in questions:
            question_text = q.get_attribute("placeholder") or q.get_attribute("name")
            if question_text:
                answer = answer_essay_question(question_text)
                q.send_keys(answer)
    except:
        print("No essay questions found or could not answer.")

    # Submit application
    try:
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_button.click()
        print("Application submitted!")
    except:
        print("Could not submit application.")

def main():
    # Scrape remote software jobs
    jobs = scrape_jobs("software developer", "remote")
    print(f"Found {len(jobs)} jobs.")

    # Apply to first 3 jobs for testing
    for job in jobs[:3]:
        apply_to_job(job["link"])
        time.sleep(5)  # Avoid overwhelming servers

    driver.quit()

if __name__ == "__main__":
    main()
