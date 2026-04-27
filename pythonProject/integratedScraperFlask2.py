from flask import Flask, render_template, redirect, url_for, request, send_file, make_response
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from gazpacho import Soup
import requests
import re
from urllib.parse import urljoin, urlparse
import html
import json
import pandas as pd
import os
import random
import time

#set up flask app + use key for session cookies to keep track of users
app = Flask(__name__)
app.secret_key = "123key456"

#login

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  #redirect user to login if not logged in

#user db in dict
users = {
    "admin": "admin",
    "keith": "keith"
}

#users class for
class User(UserMixin):
    def __init__(self, username):
        self.id = username

#load user obj froms session
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

#scrape func

def extract_data(soup):

#data dict for results
    data = {
        "title": None,
        "emails": [],
        "headings": [],
        "phone": []
    }
    


    #title
    title = soup.find("title")
    if title:
        data["title"] = title.text.strip()

    #head
    for tag in ["h1","h2","h3"]:
        elements = soup.find(tag)
        #in case a single element is returned
        if elements:
            if not isinstance(elements, list):
                elements = [elements]

            for element in elements:
                data["headings"].append(element.text.strip())

    #email
    emails = re.findall(
        r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        str(soup)
    )
    #finding reversed emails by revsersing whole html
    r_emails = re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(soup)[::-1])
                          

    #find text replaced emails
    text = str(soup)
    text = text.replace("[at]", "@").replace("(at)", "@")
    text = text.replace("[dot]", ".").replace("(dot)", ".")

    txt_replaced_emails = re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)

    #html encoded emails
    html_decoded = html.unescape(str(soup))
    html_encoded_emails = re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        html_decoded)


    #tag splitt emails
    stripped_tag_html = re.sub(r'<[^>]+>', '', str(soup))
    split_tag_emails = re.findall(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", stripped_tag_html)

    #combine lists
    all_emails = emails + r_emails + txt_replaced_emails + html_encoded_emails + split_tag_emails
    cleaned_emails = []

    for email in all_emails:
        email = email.replace("mailto:", "")
        email = email.lstrip(">")
        cleaned_emails.append(email)

    data["emails"] = list(set(cleaned_emails))

    #phone
    phones_raw = re.findall(
    r'(?<!\d)'r'(?:\+44|\+353|0)'r'[\s.\-]?'r'\d{2,5}'r'[\s.\-]?'r'\d{3,5}'r'(?:[\s.\-]?\d{3,5})?'r'(?!\d)',str(soup))

    
    phones = []
    unique_phone = set()
    for phone in phones_raw:
        digits = re.sub(r"\D", '', phone)

        if digits.startswith("44"):             #+44 numbers
            valid = len(digits) - 2 == 10
        elif digits.startswith("353"):          #+353 numbers
            valid = 8 <= len(digits) - 3 <= 9
        else:
            valid = 9 <= len(digits) <= 11      #085 or 07 etc numbers

        if valid and digits not in unique_phone:
            unique_phone.add(digits)
            phones.append(phone.strip())

    data["phone"] = phones

    return data


#crawl func
def crawl(start_url, max_pages=20):

    to_visit = [start_url]
    visited = set()
    results = []

    #set user agent 
    headers = {"User-Agent": "InfoCheck"}
    #may use for displaying in results (found _ hidden emails) 
    hidden_pages = []

    #staying on same domain
    parsed = urlparse(start_url)
    domain = parsed.netloc

    # scraping robots.txt
    robotstxt_url = parsed.scheme + "://" + domain + "/robots.txt"

    try:
        robots = requests.get(robotstxt_url)
        lines = robots.text.split("\n")

        for line in lines:
            line = line.strip()

            if line.lower().startswith("disallow"):
                #get path after 'disallow'
                path = line.split(":")[1].strip()

                if path:
                    full_path = parsed.scheme + "://" + domain + path
                    #append to_visit and hidden_pages (for possible further use)
                    to_visit.append(full_path)
                    hidden_pages.append(full_path)

    #if no robots.txt file exists / any other errors
    except Exception:
        pass
    
        
    #stops crawler from crawling over 20 pages
    while to_visit and len(visited) < max_pages:

        url = to_visit.pop(0)

        if url in visited:
            continue #skips urls already vsisted

        try:
            response = requests.get(url, timeout=5) #skips on timeout error
            soup = Soup(response.text)
        except Exception:
            continue

        #respectful delay
        time.sleep(random.uniform(1, 3))

        visited.add(url)

        #call scraper function
        data = extract_data(soup)
        data["url"] = url
        #update results
        results.append(data)

        #find links
        links = soup.find("a")
        
        #stop code from crashing if no links/1 link found
        if links:
            if not isinstance(links, list):
                links = [links]


            for link in links:

                href = link.attrs.get("href")

                if href:
                    full_url = urljoin(url, href)
                    parsed = urlparse(full_url)
                    #keep on same domain + dont visit if already visited + if not already in to_visit queue
                    if parsed.netloc == domain and full_url not in visited and full_url not in to_visit:
                        to_visit.append(full_url)

    #store results
    with open("results.json", "w") as f:
        json.dump(results, f)

    return results
     



# flask routes

#scrapings page with login required
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")

#login page
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if username in users and users[username] == password:

            user = User(username)
            login_user(user)

            return redirect(url_for("dashboard"))

    return render_template("login.html")

#runs crawler and displays results
@app.route("/scan", methods=["POST"])
@login_required
def scan():

    url = request.form["url"]

    results = crawl(url)

    #count emails, pages and phone numbers
    total_emails = 0
    for page in results:
        total_emails += len(page["emails"])

    total_phone = 0
    for page in results:
        total_phone += len(page["phone"])

    total_pages = len(results)

    summary = {"pages": total_pages, "emails": total_emails, "phone": total_phone}

    return render_template("results.html", results=results, summary=summary)

#reloads most recent results
@app.route("/results")
@login_required
def results():

    with open("results.json", "r") as f:
        data = json.load(f)

    #count emails, pages and phone numbers
    total_emails = 0
    for page in data:
        total_emails += len(page["emails"])

    total_phone = 0
    for page in data:
        total_phone += len(page["phone"])

    total_pages = len(data)

    summary = {"pages": total_pages, "emails": total_emails, "phone": total_phone}
        
    return render_template("results.html", results=data, summary=summary)

#logout user
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

#user option to download results (json)
@app.route("/download")
@login_required
def download():
    path = os.path.join(app.root_path, "results.json")
    return send_file(path, as_attachment=True, download_name="results.json")

#downloading csv results (converting json to csv)
@app.route("/download/csv")
@login_required
def download_csv():
    with open("results.json", "r") as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    #pandas used to convert to csv for browser to download 
    response = make_response(df.to_csv(index=False))
    response.headers["Content-Disposition"] = "attachment; filename=results.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

# run

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)