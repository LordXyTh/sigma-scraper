import requests
import xml.etree.ElementTree as ET
import pandas as pd
import sys
from lxml import etree
from requests_html import HTMLSession
from tqdm import tqdm
import time

# Track failed and no-iframe URLs
failed_urls = []
no_iframe_urls = []
results = []  # Store extracted iframes

# Initialize a global session
session = None

def create_session():
    """Creates a new HTML session and returns it."""
    global session
    if session is not None:
        try:
            session.close()  # Close existing session safely
        except:
            pass
    session = HTMLSession()
    return session

def log_error(message):
    """Print errors to stderr for real-time visibility."""
    print(f"❌ {message}", file=sys.stderr)

def extract_contact_iframe(url, retries=3):
    """Extracts iframes while ignoring noscript, with retries only for actual errors."""
    global session

    for attempt in range(retries):
        try:
            if session is None:
                session = create_session()

            r = session.get(url)

            # Render JavaScript with timeout (reduce from 10s to 6s to prevent hanging)
            r.html.render(timeout=6, sleep=2)

            # Parse HTML using lxml
            tree = etree.HTML(r.html.html)

            # Remove all <noscript> elements before searching for iframes
            for noscript in tree.xpath('//noscript'):
                noscript.getparent().remove(noscript)

            # Extract valid iframes
            iframes = tree.xpath("//iframe[@src]")
            extracted_iframes = []
            for iframe in iframes:
                src = iframe.get("src")
                if "contact.sigma-rh.com" in src:
                    extracted_iframes.append({
                        "page_url": url,  # Page where iframe was found
                        "src_url": src,   # Contact Sigma-RH iframe URL
                        "iframe_html": etree.tostring(iframe, encoding="unicode")  # Full iframe tag
                    })

            if extracted_iframes:
                print(f"✅ Successfully extracted iframe from {url} on attempt {attempt+1}/{retries}")
                return extracted_iframes
            
            # If no iframe found, log the URL
            print(f"⚠️ No iframe found on {url}. Logging it for review.")
            no_iframe_urls.append({"page_url": url})
            return None

        except requests.exceptions.RequestException as e:
            log_error(f"⚠️ Attempt {attempt+1}/{retries} failed for {url}: {e}")
            time.sleep(3)  # Sleep before retrying

        except Exception as e:
            log_error(f"⚠️ Attempt {attempt+1}/{retries} failed for {url}: {e}")

            # If the session is closed, restart it
            if "Session is closed" in str(e) or "RuntimeError" in str(e):
                log_error("🔄 Session closed unexpectedly, creating a new one...")
                session = create_session()
                time.sleep(2)  # Small delay to prevent rapid re-creation

            elif attempt == retries - 1:
                log_error(f"❌ Skipping {url} after {retries} failed attempts (due to errors).")
                failed_urls.append({"page_url": url})
    return None

def get_urls_from_sitemap(sitemap_url):
    """Extracts all URLs from the sitemap."""
    try:
        response = requests.get(sitemap_url, timeout=10)
        response.raise_for_status()  # Raise an error for bad responses
        root = ET.fromstring(response.content)
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        return [loc.text for loc in root.findall(".//ns:loc", ns)]
    except Exception as e:
        log_error(f"❌ Error fetching sitemap: {e}")
        return []

def run_sequentially(urls):
    """Runs all URLs sequentially to avoid crashes."""
    global session
    session = create_session()  # Initialize session once at the beginning

    for url in tqdm(urls, desc="Scraping Progress"):
        result = extract_contact_iframe(url)
        if result is not None:
            results.extend(result)  # Store iframe results

    session.close()  # Close session after scraping

def main():
    # Get the list of URLs from the sitemap
    sitemap_url = "https://www.sigma-rh.com/sitemap.xml"
    urls = get_urls_from_sitemap(sitemap_url)

    print(f"🚀 Running in sequential mode with a persistent session. Processing {len(urls)} URLs...")

    # Process URLs sequentially
    run_sequentially(urls)

    # Convert results to a DataFrame
    df_iframes = pd.DataFrame(results, columns=["page_url", "src_url", "iframe_html"])
    df_failed = pd.DataFrame(failed_urls, columns=["page_url"])
    df_no_iframe = pd.DataFrame(no_iframe_urls, columns=["page_url"])

    # Save everything to CSV at the end
    df_iframes.to_csv("sigma_iframes.csv", index=False)
    df_failed.to_csv("failed_urls.csv", index=False)
    df_no_iframe.to_csv("no_iframes.csv", index=False)

    print(f"✅ Processing complete. {len(df_iframes)} valid iframes found.")
    print(f"⚠️ {len(df_no_iframe)} URLs had no iframes (saved to no_iframes.csv).")
    print(f"⚠️ {len(df_failed)} URLs failed due to errors (saved to failed_urls.csv).")

# Run the script
if __name__ == "__main__":
    main()
