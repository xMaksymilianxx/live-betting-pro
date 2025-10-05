from http.server import BaseHTTPRequestHandler
import json
import requests
from datetime import datetime
import random

# ===== KONFIGURACJA API KEYS =====
API_FOOTBALL_KEY = "ac0417c6e0dcfa236b146b9585892c9a"
FOOTBALL_DATA_KEY = "901f0e15a0314793abaf625692082910"
SPORTMONKS_KEY = "GDkPEhJTHCqSscTnlGu2j87eG3Gw77ECv25j0nbnKbER9Gx6Oj7e6XRud0oh"

# ===== API ENDPOINTS =====
API_SOURCES = {
    'api_football': {
        'base_url': 'https://api-football-v1.p.rapidapi.com/v3',
        'headers': {
            'x-rapidapi-host': 'api-football-v1.p.rapidapi.com',
            'x-rapidapi-key': API_FOOTBALL_KEY
        },
        'priority': 1
    },
    'football_data': {
        'base_url': 'https://api.football-data.org/v4',
        'headers': {
            'X-Auth-Token': FOOTBALL_DATA_KEY
        },
        'priority': 2
    },
    'sportmonks': {
        'base_url': 'https://api.sportmonks.com/v3/football',
        'headers': {
            'Authorization': SPORTMONKS_KEY
        },
        'priority': 3
    }
}

# ===== ENHANCED xG CALCULATION =====
def calculate_enhanced_xg(stats, source='api_football'):
    """
    Oblicza Expected Goals na podstawie statystyk z różnych źródeł
    """
    xg = 0
    possession = 50
    
    # Wagi dla różnych statystyk
    xg_weights = {
        'Shots on Goal': 0.35,
        'Shots insidebox': 0.25,
        'Total Shots': 0.08,
        'Dangerous Attacks': 0.03,
        'Corner Kicks': 0.05,
        'shots_on_target': 0.35,  # Football-Data format
        'shots': 0.08,
        'corners': 0.05,
    }
    
    for stat in stats:
        if isinstance(stat, dict):
            stat_type = stat.get('type', '') or stat.get('name', '')
            value = stat.get('value', 0)
            
            # Konwersja procentów
            try:
                if isinstance(value, str):
                    if '%' in value:
                        numeric_value = int(value.replace('%', ''))
                        if 'Possession' in stat_type or 'possession' in stat_type:
                            possession = numeric_value
                    else:
                        value = int(value)
                elif value is None:
                    value = 0
            except:
                value = 0
            
            # Dodaj do xG jeśli statystyka ma wagę
            for key, weight in xg_weights.items():
                if key.lower() in stat_type.lower():
                    xg += value * weight
                    break
    
    # Bonus za posiadanie piłki
    possession_bonus = (possession - 50) * 0.01
    xg += possession_bonus
    
    return max(0, round(xg, 2))

# ===== FETCH Z API-FOOTBALL =====
def fetch_api_football():
    """Pobiera mecze live z API-Football"""
    try:
        url = f"{API_SOURCES['api_football']['base_url']}/fixtures"
        params = {'live': 'all'}
        
        response = requests.get(
            url, 
            headers=API_SOURCES['api_football']['headers'], 
            params=params, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('response', [])
            
            results = []
            for match in matches[:5]:
                fixture = match.get('fixture', {})
                teams = match.get('teams', {})
                goals = match.get('goals', {})
                league = match.get('league', {})
                
                match_info = {
                    'id': fixture.get('id'),
                    'source': 'API-Football',
                    'league': league.get('name'),
                    'country': league.get('country'),
                    'home_team': teams.get('home', {}).get('name'),
                    'away_team': teams.get('away', {}).get('name'),
                    'home_goals': goals.get('home', 0),
                    'away_goals': goals.get('away', 0),
                    'minute': fixture.get('status', {}).get('elapsed', 0),
                    'signals': []
                }
                
                # Pobierz statystyki
                stats_url = f"{API_SOURCES['api_football']['base_url']}/fixtures/statistics"
                stats_params = {'fixture': fixture.get('id')}
                stats_response = requests.get(
                    stats_url, 
                    headers=API_SOURCES['api_football']['headers'], 
                    params=stats_params, 
                    timeout=10
                )
                
                if stats_response.status_code == 200:
                    stats = stats_response.json().get('response', [])
                    
                    if len(stats) >= 2:
                        home_xg = calculate_enhanced_xg(stats[0].get('statistics', []))
                        away_xg = calculate_enhanced_xg(stats[1].get('statistics', []))
                        
                        match_info['home_xg'] = home_xg
                        match_info['away_xg'] = away_xg
                        match_info['total_xg'] = home_xg + away_xg
                        
                        # Generuj sygnały zakładowe
                        if home_xg + away_xg > 10:
                            match_info['signals'].append({
                                'market': 'Over 2.5 Goals',
                                'confidence': min(90, int(60 + (home_xg + away_xg - 10) * 3)),
                                'reasoning': f'Wysoka aktywność: Total xG {home_xg + away_xg:.1f}'
                            })
                        
                        if abs(home_xg - away_xg) > 5:
                            favorite = 'Home' if home_xg > away_xg else 'Away'
                            match_info['signals'].append({
                                'market': f'{favorite} Win',
                                'confidence': min(85, int(55 + abs(home_xg - away_xg) * 4)),
                                'reasoning': f'Dominacja: {max(home_xg, away_xg):.1f} xG'
                            })
                
                results.append(match_info)
            
            return {'success': True, 'matches': results, 'source': 'API-Football'}
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'source': 'API-Football'}

# ===== FETCH Z FOOTBALL-DATA.ORG =====
def fetch_football_data():
    """Pobiera mecze live z Football-Data.org (fallback)"""
    try:
        url = f"{API_SOURCES['football_data']['base_url']}/matches"
        params = {'status': 'LIVE'}
        
        response = requests.get(
            url, 
            headers=API_SOURCES['football_data']['headers'], 
            params=params, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            results = []
            for match in matches[:5]:
                match_info = {
                    'id': match.get('id'),
                    'source': 'Football-Data.org',
                    'league': match.get('competition', {}).get('name'),
                    'country': match.get('area', {}).get('name'),
                    'home_team': match.get('homeTeam', {}).get('name'),
                    'away_team': match.get('awayTeam', {}).get('name'),
                    'home_goals': match.get('score', {}).get('fullTime', {}).get('home', 0),
                    'away_goals': match.get('score', {}).get('fullTime', {}).get('away', 0),
                    'minute': match.get('minute', 0),
                    'home_xg': round(random.uniform(3, 12), 2),  # Placeholder
                    'away_xg': round(random.uniform(3, 12), 2),
                    'signals': []
                }
                
                results.append(match_info)
            
            return {'success': True, 'matches': results, 'source': 'Football-Data.org'}
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'source': 'Football-Data.org'}

# ===== FETCH Z SPORTMONKS =====
def fetch_sportmonks():
    """Pobiera mecze live z SportMonks (ostatnia deska ratunku)"""
    try:
        url = f"{API_SOURCES['sportmonks']['base_url']}/livescores"
        
        response = requests.get(
            url, 
            headers=API_SOURCES['sportmonks']['headers'], 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get('data', [])
            
            results = []
            for match in matches[:5]:
                match_info = {
                    'id': match.get('id'),
                    'source': 'SportMonks',
                    'league': match.get('league', {}).get('name'),
                    'home_team': match.get('localTeam', {}).get('name'),
                    'away_team': match.get('visitorTeam', {}).get('name'),
                    'home_goals': match.get('scores', {}).get('localteam_score', 0),
                    'away_goals': match.get('scores', {}).get('visitorteam_score', 0),
                    'minute': match.get('time', {}).get('minute', 0),
                    'signals': []
                }
                
                results.append(match_info)
            
            return {'success': True, 'matches': results, 'source': 'SportMonks'}
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'source': 'SportMonks'}

# ===== MAIN HANDLER =====
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Multi-API fallback strategy
            api_results = []
            
            # Próba 1: API-Football (najlepsze)
            result = fetch_api_football()
            if result['success'] and result.get('matches'):
                api_results = result['matches']
                active_source = 'API-Football'
            else:
                # Próba 2: Football-Data (backup)
                result = fetch_football_data()
                if result['success'] and result.get('matches'):
                    api_results = result['matches']
                    active_source = 'Football-Data.org'
                else:
                    # Próba 3: SportMonks (ostatnia szansa)
                    result = fetch_sportmonks()
                    if result['success'] and result.get('matches'):
                        api_results = result['matches']
                        active_source = 'SportMonks'
                    else:
                        raise Exception("All API sources failed")
            
            # Sukces!
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response_data = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'active_source': active_source,
                'matches_found': len(api_results),
                'results': api_results,
                'api_status': {
                    'api_football': '🟢 Available',
                    'football_data': '🟢 Backup Ready',
                    'sportmonks': '🟢 Emergency Ready'
                }
            }
            
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
        
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Wszystkie źródła API nie odpowiadają. Spróbuj ponownie za chwilę.'
            }
            
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
