import asyncio
import httpx
from bs4 import BeautifulSoup
import html as html_parser
import re

async def clean_html(raw_html):
    if not raw_html: return ""
    soup = BeautifulSoup(raw_html, "lxml")
    for s in soup(["script", "style", "nav", "footer", "iframe", "header", "button"]):
        s.decompose()
    text = soup.get_text(separator=' ')
    text = html_parser.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def fetch_article_body(url):
    print(f"\n--- Testing URL: {url} ---")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url)
            print(f"Status Code: {response.status_code}")
            
            soup = BeautifulSoup(response.text, "lxml")
            for s in soup(["script", "style", "nav", "footer", "header", "aside"]):
                s.decompose()

            # Junk Filter
            junk_keywords = ["cookie", "consent", "accept all", "reject all", "privacy policy", "terms of service", "subscribe now", "sign in", "loading..."]
            
            potential_bodies = soup.find_all(['div', 'article', 'section'])
            best_element = None
            max_p = 0
            for element in potential_bodies:
                p_count = len(element.find_all('p', recursive=False))
                if p_count > max_p:
                    max_p = p_count
                    best_element = element
            
            main_content = ""
            if best_element:
                paragraphs = best_element.find_all('p')
                valid_ps = [p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50 and not any(k in p.get_text().lower() for k in junk_keywords)]
                main_content = " ".join(valid_ps)
            
            if not main_content:
                paragraphs = soup.find_all('p')
                valid_ps = [p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50 and not any(k in p.get_text().lower() for k in junk_keywords)]
                main_content = " ".join(valid_ps)

            final_text = await clean_html(main_content)
            print(f"Scraped Context (First 200 chars): {final_text[:200]}...")
            return final_text
    except Exception as e:
        print(f"Error: {e}")
        return None

async def main():
    test_urls = [
        "https://www.aajtak.in/national/story/telangana-minister-bandi-sanjay-kumar-writes-letter-to-dgp-on-girl-safety-ntc-2016487-2024-04-12",
        "https://www.bbc.com/news/world-asia-68796632",
        "https://news.google.com/articles/CBMiYWh0dHBzOi8vd3d3LmluZGlhdG9kYXkuaW4vaW5kaWEvc3RvcnkvdmlyYXQta29obGktZ2xvdmVzLWhlbG1ldC1taS12cy1yY2ItaXBsLTIwMjQtMjUyNjg1Mi0yMDI0LTA0LTEy0gFlaHR0cHM6Ly93d3cuaW5kaWF0b2RheS5pbi9hbXAvaW5kaWEvc3RvcnkvdmlyYXQta29obGktZ2xvdmVzLWhlbG1ldC1taS12cy1yY2ItaXBsLTIwMjQtMjUyNjg1Mi0yMDI0LTA0LTEy"
    ]
    for url in test_urls:
        await fetch_article_body(url)

if __name__ == "__main__":
    asyncio.run(main())
