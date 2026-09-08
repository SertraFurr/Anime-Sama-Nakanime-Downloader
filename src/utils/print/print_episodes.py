from src.var import Colors, print_separator, SourceDomains

def print_episodes(episodes, wanted_episodes=None):
    SOURCE_CONFIG = {
        "vk.com": ("DEPRECATED", Colors.FAIL, False),
        "myvi.tv": ("DEPRECATED", Colors.FAIL, False),
        "oneupload.net": ("DOWN", Colors.FAIL, False),
        "oneupload.to": ("DOWN", Colors.FAIL, False),
        "myvi.top": ("Malicious", Colors.FAIL, False),
        "sendvid.com": ("SendVid", Colors.OKGREEN, True),
        "movearnpre.com": ("Movearnpre", Colors.OKGREEN, True),
        "video.sibnet.ru": ("Sibnet", Colors.OKGREEN, True),
        "vidmoly.net": ("Vidmoly", Colors.OKGREEN, True),
        "vidmoly.to": ("Vidmoly", Colors.OKGREEN, True),
        "smoothpre.com": ("Smoothpre", Colors.OKGREEN, True),
        "mivalyo.com": ("Mivalyo", Colors.OKGREEN, True),
        "dingtezuni.com": ("Dingtezuni", Colors.OKGREEN, True),
        "embed4me.com": ("Embed4me", Colors.OKGREEN, True),
        "ansembed.net": ("AnsEmbed", Colors.OKGREEN, True),
        "vidmoly.org": ("Vidmoly", Colors.OKGREEN, True),
        "vidmoly.me": ("Vidmoly", Colors.OKGREEN, True),
        "voe": ("Voe", Colors.OKGREEN, True),
        "bysesukior.com": ("Filemoon", Colors.OKGREEN, True),
        "filemoon": ("Filemoon", Colors.OKGREEN, True),
        "luluvdo.com": ("LuluStream", Colors.OKGREEN, True),
        "lulustream.com": ("LuluStream", Colors.OKGREEN, True),
        "vidzy.live": ("Vidzy", Colors.OKGREEN, True),
        "vidzy.org": ("Vidzy", Colors.OKGREEN, True),
        "vidzy": ("Vidzy", Colors.OKGREEN, True),
        "uqload.is": ("Uqload", Colors.OKGREEN, True),
        "uqload.co": ("Uqload", Colors.OKGREEN, True),
        "uqload.com": ("Uqload", Colors.OKGREEN, True),
        "uqload.to": ("Uqload", Colors.OKGREEN, True),
        "uqload": ("Uqload", Colors.OKGREEN, True),
        "nakanime.tv": ("Nakanime", Colors.OKGREEN, True),
        "nakanime": ("Nakanime", Colors.OKGREEN, True),
    }

    print(f"\n{Colors.BOLD}{Colors.HEADER}📺 AVAILABLE EPISODES{Colors.ENDC}")
    print_separator("=")
    
    for category, urls in episodes.items():
        print(f"\n{Colors.BOLD}{Colors.OKCYAN}🎮 {category}:{Colors.ENDC} ({len(urls)} episodes)")
        print_separator("─", 40)

        for i, url in enumerate(urls, start=1):
            # Un episode hors de la selection demandee n'a simplement pas ete
            # fetch (pas "indisponible" - on ne veut pas balancer des
            # centaines de lignes "Unavailable" pour des episodes que
            # l'utilisateur n'a meme pas demandes).
            if wanted_episodes and i not in wanted_episodes:
                continue

            if url is None:
                print(f"{Colors.FAIL}  {i:2d}. Episode {i} - Unavailable ❌{Colors.ENDC}")
                continue

            url_lower = url.lower()
            found = False

            if SourceDomains.is_voe_url(url, category=category):
                print(f"{Colors.OKGREEN}  {i:2d}. Episode {i} - Voe ✅{Colors.ENDC}")
                found = True
                continue
            
            for domain, (label, color, ok) in SOURCE_CONFIG.items():
                if domain in url_lower:
                    status_symbol = "✅" if ok else "❌"
                    display_label = f"{label} {status_symbol}"
                    suffix = f" - {url[:60]}..." if not ok else ""
                    
                    print(f"{color}  {i:2d}. Episode {i} - {display_label}{suffix}{Colors.ENDC}")
                    found = True
                    break
            
            if not found:
                print(f"{Colors.WARNING}  {i:2d}. Episode {i} - Unknown source ⚠️ {Colors.ENDC} {url[:60]}...")
