"""
CarJet Direct API - Parse completo com suppliers e categorias
"""
import urllib.request
import urllib.parse
from datetime import datetime
import uuid
import re
import time
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup


def to_carjet_format(dt: datetime) -> str:
    return dt.strftime('%d/%m/%Y %H:%M')


def extract_redirect_url(html: str) -> Optional[str]:
    pattern = r"window\.location\.replace\('([^']+)'\)"
    match = re.search(pattern, html)
    return match.group(1) if match else None


# Mapa de códigos para nomes de suppliers
SUPPLIER_MAP = {
    'AUP': 'Auto Prudente Rent a Car',
    'AUTOPRUDENTE': 'Auto Prudente Rent a Car',
    'THR': 'Thrifty',
    'ECR': 'Europcar',
    'HER': 'Hertz',
    'CEN': 'Centauro',
    'OKR': 'OK Mobility',
    'SUR': 'Surprice',
    'GREENMOTION': 'Greenmotion',
    'GOLDCAR': 'Goldcar',
    'SIXT': 'Sixt',
    'ICT': 'Interrent',
    'BGX': 'Budget',
    'YNO': 'YesNo',
    'KED': 'Keddy',
    'FIR': 'Firefly',
    'ALM': 'Alamo',
    'NAT': 'National',
    'ENT': 'Enterprise',
}


def normalize_supplier(name: str) -> str:
    """Converte código/nome de supplier para nome completo"""
    if not name:
        return 'CarJet'
    
    name_upper = name.upper().strip()
    
    # Tentar extrair código de logo primeiro (ex: logo_AUP.png → AUP)
    logo_match = re.search(r'logo[_-]([A-Z0-9]+)', name_upper)
    if logo_match:
        code = logo_match.group(1)
        if code in SUPPLIER_MAP:
            return SUPPLIER_MAP[code]
    
    # Tentar match direto
    if name_upper in SUPPLIER_MAP:
        return SUPPLIER_MAP[name_upper]
    
    # Normalizar nomes comuns
    for code, full_name in SUPPLIER_MAP.items():
        if code in name_upper or full_name.upper() in name_upper:
            return full_name
    
    # Se ainda não encontrou e tem logo_, retornar o código
    if logo_match:
        return logo_match.group(1).title()
    
    return name.strip()


def detect_category_from_car(car_name: str, transmission: str = '') -> str:
    """
    Detecta categoria (código apenas, sem 'Group') baseado no nome do carro
    Retorna apenas o código (B1, D, E2, etc) - o frontend faz o mapeamento
    """
    car = car_name.lower()
    trans = transmission.lower()
    auto = 'auto' in car or 'auto' in trans or 'automatic' in trans
    
    # Casos específicos primeiro
    if 'peugeot' in car and '308' in car and auto:
        return 'E2'
    if 'fiat' in car and '500l' in car:
        return 'J1'
    if 'kia' in car and 'ceed' in car:
        return 'D'
    if 'mini' in car and 'countryman' in car:
        return 'G'
    if 'caddy' in car and auto:
        return 'M2'
    if 'peugeot' in car and 'rifter' in car:
        return 'M1'
    if 'citroen' in car and 'c1' in car and auto:
        return 'E1'
    if 'citroen' in car and 'c3' in car and 'aircross' in car:
        return 'L1' if auto else 'J1'
    if 'peugeot' in car and '5008' in car:
        return 'M1'
    if 'fiat' in car and '500x' in car:
        return 'L1' if auto else 'J1'
    if 'cross' in car and ('vw' in car or 'volkswagen' in car):
        return 'L1' if auto else 'J1'
    if 'peugeot' in car and '308' in car and 'sw' in car and auto:
        return 'L2'
    
    # Categorias por tipo de veículo
    if any(x in car for x in ['fiat 500', 'citroen c1', 'toyota aygo', 'volkswagen up', 'peugeot 108', 'hyundai i10']):
        if '4' in car and 'door' in car:
            return 'B1'
        return 'E1' if auto else 'B2'
    
    if any(x in car for x in ['renault clio', 'peugeot 208', 'ford fiesta', 'seat ibiza', 'hyundai i20', 'opel corsa']):
        return 'E2' if auto else 'D'
    
    if any(x in car for x in ['juke', '2008', 'captur', 'stonic', 'kauai', 'kona']):
        return 'F'
    
    if 'mini' in car and 'cooper' in car:
        return 'G'
    
    if any(x in car for x in ['crossover', 'aircross', '500x', 't-cross', 'taigo', 'arona']):
        return 'L1' if auto else 'J1'
    
    if ('sw' in car or 'estate' in car or 'wagon' in car) and not '7' in car:
        return 'L2' if auto else 'J2'
    
    if any(x in car for x in ['3008', 'qashqai', 'c-hr', 'tiguan', 'karoq', 'tucson']):
        return 'L1' if auto else 'F'
    
    if any(x in car for x in ['lodgy', 'scenic', 'rifter', '7 seater']) or '7' in car:
        return 'M2' if auto else 'M1'
    
    if '9' in car or 'tourneo' in car or 'vito' in car or 'transporter' in car:
        return 'N'
    
    # Fallback baseado em tamanho
    if auto:
        return 'E2'
    return 'D'


def scrape_carjet_direct(location: str, start_dt: datetime, end_dt: datetime, quick: int = 0) -> List[Dict[str, Any]]:
    try:
        print(f"[DIRECT] Location: {location}, Start: {start_dt}, End: {end_dt}")
        
        location_codes = {
            'faro': 'FAO02',
            'aeroporto de faro': 'FAO02',
            'albufeira': 'ABF01',
            'lisboa': 'LIS01',
            'porto': 'OPO01',
            'funchal': 'FNC01',
            'ponta delgada': 'PDL01',
        }
        
        loc_lower = location.lower()
        pickup_code = 'FAO02'
        for key, code in location_codes.items():
            if key in loc_lower:
                pickup_code = code
                break
        
        print(f"[DIRECT] Código: {pickup_code}")
        
        pickup_date = to_carjet_format(start_dt)
        return_date = to_carjet_format(end_dt)
        session_id = str(uuid.uuid4())
        
        form_data = {
            'frmDestino': pickup_code,
            'frmDestinoFinal': '',
            'frmFechaRecogida': pickup_date,
            'frmFechaDevolucion': return_date,
            'frmHasAge': 'False',
            'frmEdad': '35',
            'frmPrvNo': '',
            'frmMoneda': 'EUR',
            'frmMonedaForzada': '',
            'frmJsonFilterInfo': '',
            'frmTipoVeh': 'CAR',
            'idioma': 'PT',
            'frmSession': session_id,
            'frmDetailCode': ''
        }
        
        encoded_data = urllib.parse.urlencode(form_data).encode('utf-8')
        url = 'https://www.carjet.com/do/list/pt'
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html',
            'Accept-Language': 'pt-PT,pt;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.carjet.com/',
            'Origin': 'https://www.carjet.com'
        }
        
        print(f"[DIRECT] POST → {url}")
        req = urllib.request.Request(url, data=encoded_data, headers=headers, method='POST')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8')
        
        print(f"[DIRECT] HTML: {len(html)} bytes")
        
        # Seguir redirect se necessário
        if 'Waiting Prices' in html or 'window.location.replace' in html:
            redirect_url = extract_redirect_url(html)
            if redirect_url:
                wait_time = 2 if quick else 4
                print(f"[DIRECT] Aguardando {wait_time}s...")
                time.sleep(wait_time)
                
                full_url = f'https://www.carjet.com{redirect_url}'
                print(f"[DIRECT] Redirect → {full_url[:80]}...")
                req2 = urllib.request.Request(full_url, headers=headers, method='GET')
                
                with urllib.request.urlopen(req2, timeout=30) as response2:
                    html = response2.read().decode('utf-8')
                
                print(f"[DIRECT] HTML final: {len(html)} bytes")
        
        items = parse_carjet_html_complete(html)
        print(f"[DIRECT API] ✅ {len(items)} carros extraídos")
        return items
        
    except Exception as e:
        print(f"[DIRECT API] ❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return []


def parse_carjet_html_complete(html: str) -> List[Dict[str, Any]]:
    """Parse completo com BeautifulSoup - extrai supplier, category, photos"""
    items = []
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Procurar blocos de carros
        car_blocks = (
            soup.find_all('article') or
            soup.find_all('div', class_=lambda x: x and ('car' in x or 'auto' in x or 'result' in x) if x else False)
        )
        
        print(f"[PARSE] {len(car_blocks)} blocos encontrados")
        
        for idx, block in enumerate(car_blocks):
            try:
                # Nome do carro
                car_name = ''
                for tag in block.find_all(['h3', 'h4', 'span', 'div']):
                    text = tag.get_text(strip=True)
                    # Verificar se parece nome de carro (tem marca conhecida)
                    if any(brand in text.lower() for brand in ['fiat', 'renault', 'peugeot', 'citroen', 'toyota', 'ford', 'vw', 'volkswagen', 'opel', 'seat', 'hyundai', 'kia', 'nissan', 'mercedes', 'bmw', 'audi', 'mini', 'jeep', 'dacia', 'skoda', 'mazda', 'mitsubishi', 'honda', 'suzuki']):
                        car_name = text
                        # Limpar texto extra ("ou similar", categorias, etc)
                        car_name = re.sub(r'\s+(ou similar|or similar).*$', '', car_name, flags=re.IGNORECASE)
                        car_name = re.sub(r'\s*\|\s*.*$', '', car_name)  # Remove "| Pequeno", "| Médio", etc
                        car_name = car_name.strip()
                        break
                
                if not car_name:
                    continue
                
                # Supplier - procurar por logo ou texto
                supplier = 'CarJet'
                img_tags = block.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    title = img.get('title', '')

                    # Logos normalmente têm /logo no path
                    if '/logo' in src.lower() or 'logo_' in src.lower():
                        supplier = normalize_supplier(src)
                        if supplier != 'CarJet':
                            break

                    # Verificar alt text
                    if alt and len(alt) <= 50 and alt.lower() not in ['car', 'vehicle', 'auto']:
                        normalized = normalize_supplier(alt)
                        if normalized != 'CarJet' and normalized != alt:
                            supplier = normalized
                            break

                    # Verificar title
                    if title and len(title) <= 50:
                        normalized = normalize_supplier(title)
                        if normalized != 'CarJet' and normalized != title:
                            supplier = normalized
                            break

                # Preço
                price = '€0.00'
                for tag in block.find_all(['span', 'div', 'p']):
                    text = tag.get_text(strip=True)
                    match = re.search(r'€?\s*(\d+(?:[.,]\d{2})?)\s*€?', text)
                    if match:
                        try:
                            price_val = float(match.group(1).replace(',', '.'))
                            if 10 < price_val < 10000:
                                price = f'€{price_val:.2f}'
                                break
                        except:
                            pass
                
                if price == '€0.00':
                    continue
                
                # Foto
                photo = ''
                for img in img_tags:
                    src = img.get('src', '')
                    # Fotos de carros normalmente têm /cars/ ou /vehicles/ no path
                    if '/car' in src.lower() or '/vehicle' in src.lower() or '/img' in src:
                        photo = src if src.startswith('http') else f'https://www.carjet.com{src}'
                        break
                
                # Transmissão
                transmission = ''
                for tag in block.find_all(['span', 'div']):
                    text = tag.get_text(strip=True).lower()
                    if 'automatic' in text or 'manual' in text:
                        transmission = 'Automatic' if 'automatic' in text else 'Manual'
                        break
                
                # Detectar categoria
                category = detect_category_from_car(car_name, transmission)
                
                items.append({
                    'id': idx,
                    'car': car_name,
                    'supplier': supplier,
                    'price': price,
                    'category': category,
                    'transmission': transmission,
                    'photo': photo,
                    'currency': 'EUR',
                    'link': '',
                })
                
            except Exception as e:
                print(f"[PARSE] Erro bloco {idx}: {e}")
                continue
        
        print(f"[PARSE] {len(items)} items válidos")
        
    except Exception as e:
        print(f"[PARSE ERROR] {e}")
        import traceback
        traceback.print_exc()
    
    return items
