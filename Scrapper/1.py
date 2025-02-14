import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
import os
from aiohttp_retry import RetryClient, ExponentialRetry
from asyncio import CancelledError
from aiohttp.client_exceptions import ServerDisconnectedError, ClientOSError, ClientResponseError
import re
import subprocess

# Maximum concurrent requests
SEM_LIMIT = 5
semaphore = asyncio.Semaphore(SEM_LIMIT)

def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)
# Fetches the page content asynchronously
async def fetch_page(session, url):
    async with semaphore:
        try:
            async with session.get(url, timeout=30) as response:
                return await response.text()
        except (ServerDisconnectedError, ClientOSError, ClientResponseError) as e:
            print(f"Error fetching {url}: {e}")
            await asyncio.sleep(5)  # Wait before retrying
            return None

async def fetchLinks(session):
    years = [2021]
    urls = [f"https://papers.nips.cc/paper/{year}" for year in years]
    tasks = [fetch_page(session, url) for url in urls]
    pages = await asyncio.gather(*tasks)

    for i, page in enumerate(pages):
        if page:
            extract_paper_details(page, years[i])
            with open(f'page_{years[i]}.html', 'w', encoding='utf-8') as file:
                file.write(page)

    return urls

# Extracts paper details from a single page
def extract_paper_details(html, year):
    soup = BeautifulSoup(html, 'html.parser')
    papers = []
    for paper in soup.select(".container-fluid .col ul li"):
        title = paper.select_one("a").text.strip()
        link = "https://papers.nips.cc" + paper.select_one("a")["href"]
        papers.append({"title": title, "link": link})

    print(f"Found {len(papers)} papers for {year}.")
    
    with open(f'papers_{year}.json', 'w', encoding='utf-8') as file:
        json.dump(papers, file, ensure_ascii=False, indent=4)
    return papers

# Fetches the PDF link from a paper page with retry mechanism
async def fetch_pdf_link(session, paper):
    async with semaphore:
        try:
            async with session.get(paper['link'], timeout=30) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                pdf_link_tag = soup.find('a', string='Paper')
                if pdf_link_tag:
                    pdf_link = "https://papers.nips.cc" + pdf_link_tag['href']
                    return {"title": paper['title'], "pdf_link": pdf_link}
        except (CancelledError, ServerDisconnectedError, ClientOSError, ClientResponseError) as e:
            print(f"Request error for {paper['title']}: {e}")
            await asyncio.sleep(5)  # Delay before retrying
        return {"title": paper['title'], "pdf_link": None}

# Fetches PDF links for all papers in a given year
async def fetch_pdf_links(session, year):
    print(f"lets goooo and fetch {year}")
    try:
        with open(f'papers_{year}.json', 'r', encoding='utf-8') as file:
            papers = json.load(file)
        
        tasks = [fetch_pdf_link(session, paper) for paper in papers]
        pdf_links = await asyncio.gather(*tasks)

        with open(f'pdf_links_{year}.json', 'w', encoding='utf-8') as file:
            json.dump(pdf_links, file, ensure_ascii=False, indent=4)
    except FileNotFoundError:
        print(f"File not found: papers_{year}.json")

# Downloads a single PDF file
async def download_pdf(session, paper, year):
    async with semaphore:
        pdf_link = paper['pdf_link']
        if pdf_link:
            try:
                async with session.get(pdf_link, timeout=60) as response:
                    pdf_content = await response.read()
                    sanitized_title = sanitize_filename(paper['title'])
                    pdf_path = os.path.join(f'pdf_{year}', f"{sanitized_title}.pdf")
                    os.makedirs(f'pdf_{year}', exist_ok=True)
                    with open(pdf_path, 'wb') as pdf_file:
                        pdf_file.write(pdf_content)
                    print(f"Downloaded: {paper['title']}")
            except (ServerDisconnectedError, ClientOSError, ClientResponseError) as e:
                print(f"Failed to download {paper['title']}: {e}")
                await asyncio.sleep(5)

# Downloads all PDFs for a given year
async def download_pdfs(session, year):
    try:
        with open(f'pdf_links_{year}.json', 'r', encoding='utf-8') as file:
            papers = json.load(file)

        tasks = [download_pdf(session, paper, year) for paper in papers if paper['pdf_link']]
        await asyncio.gather(*tasks)
    except FileNotFoundError:
        print(f"File not found: pdf_links_{year}.json")

# Main coroutine to orchestrate all tasks
async def main():
    retry_options = ExponentialRetry(attempts=5)
    async with RetryClient(raise_for_status=False, retry_options=retry_options) as session:
        await fetchLinks(session)
        years = [2021]
        for year in years:
            await fetch_pdf_links(session, year)
            await download_pdfs(session, year)
    
    # Execute 2.py after completing tasks
    subprocess.run(["python", "./2.py"])

if __name__ == '__main__':
    asyncio.run(main())
