import json
import os
import requests
from src.var import Colors, print_status

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')


def get_cookies():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            cf_clearance = config.get('cf_clearance_cookie', '')
            headers = config.get('headers', {})
            if cf_clearance == "" or not headers.get("User-Agent"):
                return False
            return cf_clearance, headers
    except FileNotFoundError:
        return False


def set_cookies(cf_clearance_value, user_agent_value):
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    config['cf_clearance_cookie'] = cf_clearance_value
    config['headers'] = {"User-Agent": user_agent_value}

    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)


def get_setting(key, default=None):
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            return config.get(key, default)
    except FileNotFoundError:
        return default


def set_setting(key, value):
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            pass

    config[key] = value

    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)


def get_domain_cookies(domain):
    """Generic per-domain cf_clearance store (used for sites other than the
    main configured domain, e.g. nakanime.tv) - separate from the single
    cf_clearance_cookie/headers pair above so setting one site's cookie never
    overwrites another's."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        entry = config.get('domain_cookies', {}).get(domain)
        if not entry or not entry.get('cf_clearance') or not entry.get('user_agent'):
            return False
        return entry['cf_clearance'], {"User-Agent": entry['user_agent']}
    except FileNotFoundError:
        return False


def set_domain_cookies(domain, cf_clearance_value, user_agent_value):
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    store = config.setdefault('domain_cookies', {})
    store[domain] = {"cf_clearance": cf_clearance_value, "user_agent": user_agent_value}

    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)


def check_domain_cookies(domain, headers, test_url=None, extra_headers=None):
    """test_url: when the Cloudflare rule only covers part of the site (e.g.
    franime's API), check against a URL under that rule instead of the home
    page, which can answer 200 even with an expired cookie."""
    stored = get_domain_cookies(domain)
    if stored is False:
        return False

    cf_clearance_value, stored_headers = stored

    if headers.get("User-Agent") != stored_headers.get("User-Agent"):
        return False

    request_headers = headers.copy()
    request_headers.update(extra_headers or {})
    request_headers['Cookie'] = f'cf_clearance={cf_clearance_value}'

    try:
        req = requests.get(test_url or f"https://{domain}", headers=request_headers, timeout=10)
        return req.status_code != 403
    except requests.RequestException:
        return False


def check_cookies(domain, headers):
    stored = get_cookies()
    if stored is False:
        print_status("No Cloudflare cookie stored.", "error")
        return False

    cf_clearance_value, stored_headers = stored

    if headers.get("User-Agent") != stored_headers.get("User-Agent"):
        print_status(
            "Headers do not match the User-Agent used when the cookie was set. Please use the same User-Agent.",
            "error"
        )
        return False

    request_headers = headers.copy()
    request_headers['Cookie'] = f'cf_clearance={cf_clearance_value}'

    try:
        req = requests.get(f"https://{domain}", headers=request_headers, timeout=10)
        if req.status_code != 403:
            print_status("Cloudflare cookies are valid.", "success")
            return True
        else:
            print_status("Cloudflare cookies are invalid or expired.", "error")
            return False
    except requests.RequestException as e:
        print_status(f"Request failed: {e}", "error")
        return False
