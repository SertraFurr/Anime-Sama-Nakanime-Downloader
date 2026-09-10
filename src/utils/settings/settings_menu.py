import os
from src.var import Colors, print_header, print_separator, print_status
from src.utils.config.config import get_setting, set_setting

def settings_menu():
    while True:
        print_header()
        print(f"\n{Colors.BOLD}{Colors.HEADER}⚙️ CONFIGURATION{Colors.ENDC}")
        print_separator()
        
        current_template = get_setting("save_template", "./videos/{anime}/{season}")
        current_id_mode = get_setting("identification_mode", "mal")
        current_tvdb_key = get_setting("tvdb_api_key", "")
        tvdb_key_display = (current_tvdb_key[:4] + "…") if current_tvdb_key else f"{Colors.FAIL}not set{Colors.ENDC}"

        print(f"{Colors.OKCYAN}1. Change Save Path Template{Colors.ENDC}")
        print(f"   {Colors.WARNING}Current: {current_template}{Colors.ENDC}")
        print(f"   {Colors.FAIL}Keywords: {{anime}}, {{season}}{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}2. Change Plex Identification Method{Colors.ENDC}")
        print(f"   {Colors.WARNING}Current: {current_id_mode}{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}3. Set TVDB API Key{Colors.ENDC} {Colors.FAIL}(requires a free account, see below){Colors.ENDC}")
        print(f"   {Colors.WARNING}Current: {tvdb_key_display}{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}0. Back to Main Menu{Colors.ENDC}")
        print_separator()

        choice = input(f"{Colors.BOLD}Select option: {Colors.ENDC}").strip()

        if choice == '1':
            print(f"\n{Colors.BOLD}Enter new save path template:{Colors.ENDC}")
            print(f"You can use keywords {Colors.WARNING}{{anime}}{Colors.ENDC} and {Colors.WARNING}{{season}}{Colors.ENDC} which will be automatically replaced.")
            print(f"You can also remove them if you want a simpler structure.")
            print(f"\n{Colors.BOLD}Examples (for anime 'Roshidere' season 'saison1'):{Colors.ENDC}")
            print(f" - ./videos/{{anime}}/{{season}}   →  ./videos/Roshidere/saison1/")
            print(f" - ./videos/{{anime}}            →  ./videos/Roshidere/")
            print(f" - C:/Downloads/{{season}}       →  C:/Downloads/saison1/")
            print(f" - ./MyAnimeFolder/             →  ./MyAnimeFolder/ (All files in one folder)")
            
            new_template = input(f"{Colors.BOLD}Template: {Colors.ENDC}").strip()
            if new_template:
                set_setting("save_template", new_template)
                print_status("Save path template updated!", "success")
            else:
                print_status("Cancelled.", "warning")
            input("Press Enter to continue...")

        elif choice == '2':
            print(f"\n{Colors.BOLD}How should downloaded seasons be identified to Plex?{Colors.ENDC}")
            print(f" - {Colors.OKCYAN}mal{Colors.ENDC}      : write a .match file with the MyAnimeList id "
                  f"(for the {Colors.OKCYAN}MyAnimeList.bundle{Colors.ENDC} Plex agent - default)")
            print(f" - {Colors.OKCYAN}external{Colors.ENDC} : tag the folder name instead - "
                  f"[tvdb-XXXX] or [imdbid-ttXXXXXXX] (for {Colors.OKCYAN}TheTVDB{Colors.ENDC}/IMDb-based Plex agents; "
                  f"you type the exact tag once per anime when prompted)")
            print(f" - {Colors.OKCYAN}none{Colors.ENDC}     : do nothing - no .match file, no folder tag, "
                  f"no prompts at all (same as always passing {Colors.OKCYAN}--no-mal{Colors.ENDC})")
            new_mode = input(f"{Colors.BOLD}Mode (mal/external/none): {Colors.ENDC}").strip().lower()
            if new_mode in ("mal", "external", "none"):
                set_setting("identification_mode", new_mode)
                print_status(f"Identification method set to '{new_mode}'.", "success")
            else:
                print_status("Cancelled (must be mal, external or none).", "warning")
            input("Press Enter to continue...")

        elif choice == '3':
            print(f"\n{Colors.BOLD}TVDB API Key{Colors.ENDC}")
            print(f"Only needed for the 'external' identification mode's TVDB search results")
            print(f"(without a key, only IMDb search results are shown - IMDb needs no key).")
            print(f"{Colors.BOLD}This REQUIRES a free TheTVDB account:{Colors.ENDC}")
            print(f"  1. Create a free account at {Colors.OKCYAN}https://thetvdb.com/auth/register{Colors.ENDC}")
            print(f"  2. Go to {Colors.OKCYAN}https://thetvdb.com/api-information{Colors.ENDC} and generate a")
            print(f"     'User Supported' API key (no cost, personal use)")
            print(f"  3. Paste that key below")
            new_key = input(f"{Colors.BOLD}TVDB API key (blank to clear): {Colors.ENDC}").strip()
            set_setting("tvdb_api_key", new_key)
            if new_key:
                print_status("TVDB API key saved.", "success")
            else:
                print_status("TVDB API key cleared - TVDB search results disabled.", "warning")
            input("Press Enter to continue...")

        elif choice == '0':
            break
        else:
            print_status("Invalid option", "error")
