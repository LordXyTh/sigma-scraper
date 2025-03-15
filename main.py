import asyncio
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import sys
from lxml import etree
from requests_html import AsyncHTMLSession
from tqdm import tqdm

# Track failed and no-iframe URLs
failed_urls = []
no_iframe_urls = []

def log_error(message):
    """Print errors to stderr for real-time visibility."""
    print(f"❌ {message}", file=sys.stderr)

async def extract_contact_iframe(url, retries=3):
    """Extracts iframes while ignoring noscript, with retries only for actual errors."""
    session = AsyncHTMLSession()
    
    for attempt in range(retries):
        try:
            r = await session.get(url)
            await asyncio.sleep(2)  # Prevent rapid-fire requests

            # Render JavaScript with increased timeout
            await r.html.arender(timeout=30)

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

        except Exception as e:
            log_error(f"⚠️ Attempt {attempt+1}/{retries} failed for {url}: {e}")
            await asyncio.sleep(5)  # Wait before retrying

    # If all attempts fail due to actual errors, add to failed_urls list
    log_error(f"❌ Skipping {url} after {retries} failed attempts (due to errors).")
    failed_urls.append(url)
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
    results = []
    
    # Process URLs sequentially with a progress bar
    for url in tqdm(urls, desc="Scraping Progress"):
        result = asyncio.run(extract_contact_iframe(url))
        if result is not None:
            results.extend(result)

    return results

def main():
    # Get the list of URLs from the sitemap
    sitemap_url = "https://www.sigma-rh.com/sitemap.xml"
    urls = get_urls_from_sitemap(sitemap_url)

    print(f"🚀 Running in sequential mode. Processing {len(urls)} URLs...")

    # Process URLs sequentially
    results = run_sequentially(urls)

    # Convert results to a DataFrame
    df = pd.DataFrame(results, columns=["page_url", "src_url", "iframe_html"])

    # Save DataFrame to CSV
    output_file = "sigma_iframes.csv"
    df.to_csv(output_file, index=False)

    # Save failed URLs to a separate file
    if failed_urls:
        failed_file = "failed_urls.txt"
        with open(failed_file, "w") as f:
            for url in failed_urls:
                f.write(url + "\n")
        print(f"⚠️ {len(failed_urls)} URLs failed due to errors and were saved to {failed_file}")

    # Save "No iframe found" URLs to a CSV
    if no_iframe_urls:
        no_iframe_df = pd.DataFrame(no_iframe_urls, columns=["page_url"])
        no_iframe_file = "no_iframes.csv"
        no_iframe_df.to_csv(no_iframe_file, index=False)
        print(f"⚠️ {len(no_iframe_urls)} URLs had no iframes and were saved to {no_iframe_file}")

    print(f"✅ Processing complete. {len(df)} valid iframes found. Results saved to {output_file}.")

# Run the script
if __name__ == "__main__":
    main()
