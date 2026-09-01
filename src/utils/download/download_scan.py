import requests
import json
import re
import shutil
import zipfile
from src.var import Colors, print_status, print_separator, get_domain
from src.utils.extract.extract_anime_name import extract_anime_name
import os
from tqdm import tqdm


def package_chapter_as_cbz(chap_dir, cbz_path):
    pages = sorted(
        (f for f in os.listdir(chap_dir) if os.path.isfile(os.path.join(chap_dir, f))),
        key=lambda f: (float(os.path.splitext(f)[0]) if os.path.splitext(f)[0].replace('.', '', 1).isdigit() else os.path.splitext(f)[0])
    )
    if not pages:
        return False

    with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_STORED) as cbz:
        for page in pages:
            cbz.write(os.path.join(chap_dir, page), arcname=page)

    return True

def download_scan(url, headers):
    try:
        print_status("Fetching scan page to find ID...", "info")
        page_response = requests.get(url, headers=headers, timeout=15)
        page_response.raise_for_status()
        html = page_response.text

        scan_path_match = re.search(r'id=["\']scansPlacement["\'].*?src=["\'](?:[^"\']*/)?s2/scans/([^/]+)/', html, re.DOTALL)
        if not scan_path_match:
            scan_path_match = re.search(r'src=["\'](?:[^"\']*/)?s2/scans/([^/]+)/', html)
        
        if scan_path_match:
            anime_name = scan_path_match.group(1)
            print_status(f"Found anime name from scan paths: '{anime_name}'", "success")
        else:
            id_match = re.search(r'id=["\']titreOeuvre["\'][^>]*>(.*?)<', html, re.DOTALL)
            if id_match:
                anime_name = id_match.group(1).strip('\r\n\t')
                print_status(f"Found oeuvre ID (from HTML): '{anime_name}'", "success")
            else:
                anime_name = extract_anime_name(url)
                if anime_name and anime_name[0].islower():
                     anime_name = anime_name.capitalize()
                print_status(f"Could not find ID in HTML, trying: {anime_name}", "warning")

        from urllib.parse import quote
        encoded_anime_name = quote(anime_name)
        api_url = f"https://{get_domain()}/s2/scans/get_nb_chap_et_img.php?oeuvre={encoded_anime_name}"
        
        print_status(f"Fetching chapters for: {anime_name}", "info")
        response = requests.get(api_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        try:
            chapters_data = response.json()
        except json.JSONDecodeError:
            print_status("Received invalid JSON from Anime-Sama API.", "error")
            return

        if not chapters_data:
            print_status(f"No chapters found for {anime_name}.", "warning")
            return

        if "error" in chapters_data:
            print_status(f"API Error: {chapters_data['error']}", "error")
            return

        try:
            sorted_chapters = sorted(chapters_data.keys(), key=lambda x: float(x))
        except ValueError:
            sorted_chapters = sorted(chapters_data.keys())

        print(f"\n{Colors.BOLD}{Colors.HEADER}📖 AVAILABLE CHAPTERS - {anime_name.upper()}{Colors.ENDC}")
        print_separator()

        max_chap_len = max(len(c) for c in sorted_chapters)
        col_width = max_chap_len + 10
        
        term_width = 100
        cols = max(1, term_width // col_width)
        
        chunked = [sorted_chapters[i:i + cols] for i in range(0, len(sorted_chapters), cols)]
        
        count = 0
        for row in chunked:
            line_parts = []
            for chap in row:
                page_count = chapters_data[chap]
                part = f"{Colors.OKCYAN}{chap:<{max_chap_len}}{Colors.ENDC} ({page_count}p)"
                line_parts.append(f"{part:<{col_width + 10}}")
            print("".join(line_parts))
            count += len(row)

        print_separator()
        print(f"{Colors.OKGREEN}Total: {len(sorted_chapters)} chapters available.{Colors.ENDC}")
        
        while True:
            try:
                user_input = input(f"\n{Colors.BOLD}Select chapters (e.g. 1, 10-20, all): {Colors.ENDC}").strip().lower()
                
                if not user_input:
                    continue
                
                if user_input == 'exit' or user_input == 'q':
                    return

                selected_chapters = []
                
                if user_input == 'all':
                    selected_chapters = sorted_chapters
                else:
                    parts = user_input.split(',')
                    for part in parts:
                        part = part.strip()
                        if '-' in part:
                            try:
                                start_s, end_s = part.split('-', 1)
                                start = float(start_s)
                                end = float(end_s)
                                
                                for chap in sorted_chapters:
                                    try:
                                        val = float(chap)
                                        if start <= val <= end:
                                            if chap not in selected_chapters:
                                                selected_chapters.append(chap)
                                    except ValueError:
                                        pass
                            except ValueError:
                                print_status(f"Invalid range format: {part}", "warning")
                        else:
                            if part in chapters_data:
                                if part not in selected_chapters:
                                    selected_chapters.append(part)
                            else:
                                found = False
                                try:
                                    target_val = float(part)
                                    for chap in sorted_chapters:
                                        if float(chap) == target_val:
                                            if chap not in selected_chapters:
                                                selected_chapters.append(chap)
                                            found = True
                                            break
                                except ValueError:
                                    pass
                                
                                if not found:
                                    print_status(f"Chapter {part} not found.", "warning")

                if not selected_chapters:
                    print_status("No valid chapters selected.", "error")
                    continue
                
                selected_chapters.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else x)
                
                print_status(f"Selected {len(selected_chapters)} chapters.", "success")
                print(f"Sample: {', '.join(selected_chapters[:5])}..." if len(selected_chapters) > 5 else f"List: {', '.join(selected_chapters)}")
                
                confirm = input(f"{Colors.BOLD}Confirm download? (y/n): {Colors.ENDC}").strip().lower()
                if confirm in ['y', 'yes', '1']:
                     break
                else:
                    print_status("Selection cancelled.", "info")
            
            except KeyboardInterrupt:
                return

        if not selected_chapters:
            return

        cbz_choice = input(f"{Colors.BOLD}Package chapters as .cbz? (y/n): {Colors.ENDC}").strip().lower()
        package_as_cbz = cbz_choice in ['y', 'yes', '1']

        base_scan_url = url.rstrip('/')
        local_name = anime_name
        local_name = re.sub(r'[<>:"/\\|?*]', '', local_name)
        local_name = local_name.strip()
        local_name = re.sub(r'[ .]+$', '', local_name)
        
        save_base_dir = os.path.normpath(os.path.join("scans", local_name))
        os.makedirs(save_base_dir, exist_ok=True)
        
        print_separator()
        print_status(f"Downloading scans to: {os.path.abspath(save_base_dir)}", "info")
        print_separator()

        total_chapters = len(selected_chapters)
        
        for idx, chap in enumerate(selected_chapters, 1):
            page_count = chapters_data[chap]
            safe_chap = re.sub(r'[<>:"/\\|?*]', '', str(chap)).strip()
            chap_dir = os.path.join(save_base_dir, f"Chapter {safe_chap}")
            os.makedirs(chap_dir, exist_ok=True)
            
            print(f"{Colors.BOLD}Chapter {chap} ({idx}/{total_chapters}) - {page_count} pages{Colors.ENDC}")
            scan_base_url = f"https://{get_domain()}/s2/scans/{encoded_anime_name}"
            success_count = 0
            
            loop = tqdm(range(1, int(page_count) + 1), unit="img", leave=False)
            for page_num in loop:
                extensions = ['.jpg', '.png', '.jpeg', '.webp']
                downloaded = False
                
                for ext in extensions:
                    img_url = f"{scan_base_url}/{chap}/{page_num}{ext}"
                    save_path = os.path.join(chap_dir, f"{page_num}{ext}")
                    
                    if os.path.exists(save_path):
                        downloaded = True
                        break
                    
                    try:
                        img_res = requests.get(img_url, headers=headers, stream=True, timeout=10)
                        if img_res.status_code == 200:
                            with open(save_path, 'wb') as f:
                                for chunk in img_res.iter_content(1024):
                                    f.write(chunk)
                            downloaded = True
                            break
                    except:
                        pass
                
                if downloaded:
                    success_count += 1
                else:
                    pass
            
            loop.close()
            
            if success_count == int(page_count):
                print_status(f"Chapter {chap} completed ({success_count}/{page_count})", "success")
            else:
                print_status(f"Chapter {chap} partial ({success_count}/{page_count})", "warning")

            if package_as_cbz:
                cbz_path = os.path.join(save_base_dir, f"Chapter {safe_chap}.cbz")
                try:
                    if package_chapter_as_cbz(chap_dir, cbz_path):
                        shutil.rmtree(chap_dir)
                        print_status(f"Chapter {chap} packaged as {os.path.basename(cbz_path)}", "success")
                    else:
                        print_status(f"Chapter {chap}: no pages to package into .cbz", "warning")
                except Exception as e:
                    print_status(f"Failed to package chapter {chap} as .cbz: {e}", "error")

    except requests.RequestException as e:
        print_status(f"Network error: {e}", "error")
    except Exception as e:
        print_status(f"Unexpected error: {e}", "error")
