import httpx
import lxml.html
import logging

def scrape_job_url(url):
    """
    Fetches the HTML content of the job posting URL and parses out
    only the clean text description (removing script, style, and navigation tags).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Fetch the URL content
        response = httpx.get(url, follow_redirects=True, headers=headers, timeout=10.0)
        response.raise_for_status()

        # Parse DOM
        document = lxml.html.fromstring(response.content)

        # Strip standard non-content layout elements
        for tag in ["script", "style", "noscript", "iframe", "header", "footer", "nav", "svg"]:
            for element in document.xpath(f"//{tag}"):
                element.getparent().remove(element)

        # Extract clean content text
        text = document.text_content()

        # Break text into clean lines and remove empty space lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = '\n'.join(chunk for chunk in chunks if chunk)

        if not cleaned_text.strip():
            return {"text": None, "error": "No readable text content could be extracted from the webpage."}

        return {"text": cleaned_text, "error": None}

    except Exception as e:
        logging.error(f"URL scraping error: {e}")
        return {"text": None, "error": str(e)}
