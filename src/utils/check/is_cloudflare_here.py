import requests

def check_if_cloudflare_enabled(domain, headers):
    try:
        response = requests.get(f"https://{domain}/", headers=headers, timeout=10)
        if "/catalogue" not in response.text:
            return True
        return False
    except requests.RequestException:
        return False


def check_if_url_blocked(url, headers):
    """For sites where only part of the site (e.g. an API) sits behind the
    Cloudflare challenge: the home page answers fine, but this URL says 403."""
    try:
        return requests.get(url, headers=headers, timeout=10).status_code == 403
    except requests.RequestException:
        return False
