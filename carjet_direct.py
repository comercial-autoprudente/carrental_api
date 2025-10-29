"""
CarJet Direct API - Método direto sem browser/scraping
Baseado no server.py do auto-prudente-checkin
"""
import urllib.request
import urllib.parse
from datetime import datetime
import uuid
import re
import time
from typing import List, Dict, Any, Optional


def to_carjet_format(dt: datetime) -> str:
    """Converte datetime para formato CarJet DD/MM/YYYY HH:MM"""
    return dt.strftime('%d/%m/%Y %H:%M')


def extract_redirect_url(html: str) -> Optional[str]:
    """Extrai URL de redirect do JavaScript"""
    pattern = r"window\.location\.replace\('([^']+)'\)"
    match = re.search(pattern, html)
    return match.group(1) if match else None


def scrape_carjet_direct(location: str, start_dt: datetime, end_dt: datetime, quick: int = 0) -> List[Dict[str, Any]]:
    """
    Faz request direto para API do CarJet sem usar browser
    
    Args:
        location: Nome da localização (ex: "Aeroporto de Faro", "Albufeira")
        start_dt: Data/hora de levantamento
        end_dt: Data/hora de devolução
        quick: Se 1, espera menos tempo
        
    Returns:
        Lista de dicionários com dados dos carros
    """
    try:
        # Mapear localização para código CarJet
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
        pickup_code = None
        for key, code in location_codes.items():
            if key in loc_lower:
                pickup_code = code
                break
        
        if not pickup_code:
            pickup_code = 'FAO02'  # Default para Faro
        
        # Converter datas para formato CarJet
        pickup_date = to_carjet_format(start_dt)
        return_date = to_carjet_format(end_dt)
        
        # Gerar session ID
        session_id = str(uuid.uuid4())
        
        # Preparar dados para CarJet
        form_data = {
            'frmDestino': pickup_code,
            'frmDestinoFinal': '',  # Mesmo local
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
        
        # Fazer request para CarJet
        encoded_data = urllib.parse.urlencode(form_data).encode('utf-8')
        url = 'https://www.carjet.com/do/list/pt'
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-PT,pt;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.carjet.com/',
            'Origin': 'https://www.carjet.com'
        }
        
        req = urllib.request.Request(url, data=encoded_data, headers=headers, method='POST')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8')
        
        # Verificar se é página de loading
        if 'Waiting Prices' in html or 'window.location.replace' in html:
            redirect_url = extract_redirect_url(html)
            
            if redirect_url:
                # Aguardar processamento (menos tempo se quick=1)
                wait_time = 2 if quick else 4
                time.sleep(wait_time)
                
                # Seguir redirect
                full_url = f'https://www.carjet.com{redirect_url}'
                req2 = urllib.request.Request(full_url, headers=headers, method='GET')
                
                with urllib.request.urlopen(req2, timeout=30) as response2:
                    html = response2.read().decode('utf-8')
        
        # Parse HTML para extrair dados
        items = parse_carjet_html(html)
        
        print(f"[DIRECT API] ✅ Encontrados {len(items)} carros via método direto")
        return items
        
    except Exception as e:
        print(f"[DIRECT API] ❌ Erro: {e}")
        return []


def parse_carjet_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse simples do HTML do CarJet
    Retorna lista de carros com preços
    """
    items = []
    
    try:
        # Contar artigos/ofertas
        total_cars = html.count('class="auto-box"') or html.count('<article')
        
        # Extrair preços com regex
        price_pattern = r'€\s*(\d+(?:[.,]\d{2})?)'
        price_matches = re.findall(price_pattern, html)
        
        prices = []
        for match in price_matches:
            try:
                price = float(match.replace(',', '.'))
                if 10 < price < 10000:
                    prices.append(price)
            except:
                pass
        
        # Extrair nomes de carros (simplificado)
        car_pattern = r'class="name[^"]*"[^>]*>([^<]+)</[^>]+>'
        car_matches = re.findall(car_pattern, html, re.IGNORECASE)
        
        # Combinar dados
        for i in range(min(len(car_matches), len(prices))):
            items.append({
                'id': i,
                'car': car_matches[i].strip(),
                'price': f'€{prices[i]:.2f}',
                'supplier': 'CarJet',  # Simplificado
                'currency': 'EUR',
                'category': '',
                'transmission': '',
                'photo': '',
                'link': '',
            })
        
        # Se não conseguiu parse detalhado, criar entrada genérica
        if not items and total_cars > 0:
            for i in range(min(total_cars, len(prices))):
                items.append({
                    'id': i,
                    'car': f'Car {i+1}',
                    'price': f'€{prices[i]:.2f}' if i < len(prices) else '€0.00',
                    'supplier': 'CarJet',
                    'currency': 'EUR',
                    'category': '',
                    'transmission': '',
                    'photo': '',
                    'link': '',
                })
        
    except Exception as e:
        print(f"[PARSE ERROR] {e}")
    
    return items
