from flask import Flask, jsonify, request
import requests
import re

app = Flask(__name__)

def format_imdb_id(imdb_id):
    """Formatear IMDb ID"""
    if not imdb_id.startswith('tt'):
        imdb_id = f"tt{imdb_id}"
    return imdb_id

def validate_imdb_id(imdb_id):
    """Validar formato de IMDb ID"""
    if not imdb_id or len(imdb_id) < 7:
        return False
    return True

@app.route('/')
def root():
    """Información básica de la API"""
    return jsonify({
        "name": "IMDb API Local - Vercel",
        "version": "1.0.0",
        "status": "running",
        "platform": "vercel",
        "endpoints": [
            "GET /health",
            "GET /imdb/<imdb_id>/season/<season>/episode/<episode>/rating"
        ]
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "platform": "vercel",
        "message": "API funcionando correctamente"
    })

def try_ajax_episodes(imdb_id, season, episode):
    """Intentar obtener episodio usando el endpoint AJAX de IMDb con paginación inteligente"""
    try:
        # Para episodios altos, necesitamos calcular el rango correcto
        # IMDb carga en bloques de ~50 episodios
        start_index = max(0, ((episode - 1) // 50) * 50)
        
        ajax_url = f"https://www.imdb.com/title/{imdb_id}/episodes/_ajax"
        params = {
            'season': season,
            'start': start_index
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f"https://www.imdb.com/title/{imdb_id}/episodes/?season={season}"
        }
        
        response = requests.get(ajax_url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            html = response.text
            
            # Buscar el episodio específico en la respuesta AJAX
            # Patrones más flexibles para encontrar el episodio
            episode_patterns = [
                rf'S{season}\.E{episode}\s*∙\s*([^<]+)</div>.*?(\d+\.\d+)</span>.*?\(<!-- -->(\d+)<!-- -->\)',
                rf'S{season}\.E{episode}[^>]*>([^<]+)<.*?(\d+\.\d+)</span>.*?\((\d+)\)',
                rf'episode-{episode}.*?(\d+\.\d+)</span>.*?\((\d+)\)'
            ]
            
            for pattern in episode_patterns:
                match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                if match:
                    if len(match.groups()) >= 3:
                        title = match.group(1).strip()
                        rating = float(match.group(2))
                        votes = match.group(3)
                    else:
                        title = f"Episode {episode}"
                        rating = float(match.group(1))
                        votes = match.group(2)
                    
                    return {
                        "title": title,
                        "rating": rating,
                        "votes": votes,
                        "success": True,
                        "method": "ajax"
                    }
        
        return None
    except Exception as e:
        print(f"Error en AJAX: {e}")  # Para debugging
        return None

def try_load_all_episodes(imdb_id, season, episode):
    """Cargar todos los episodios usando el parámetro 'mode=all' de IMDb"""
    try:
        # IMDb tiene un parámetro para cargar todos los episodios de una vez
        url = f"https://www.imdb.com/title/{imdb_id}/episodes/?season={season}&mode=all"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            html = response.text
            
            # Buscar el episodio específico con patrones más flexibles
            episode_patterns = [
                rf'S{season}\.E{episode}\s*∙\s*([^<]+)</div>.*?(\d+\.\d+)</span>.*?\(<!-- -->(\d+)<!-- -->\)',
                rf'S{season}\.E{episode}[^>]*>([^<]+)<.*?(\d+\.\d+)</span>.*?\((\d+)\)',
                rf'episode.*?{episode}.*?(\d+\.\d+)</span>.*?\((\d+)\)'
            ]
            
            for pattern in episode_patterns:
                match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                if match:
                    if len(match.groups()) >= 3:
                        title = match.group(1).strip()
                        rating = float(match.group(2))
                        votes = match.group(3)
                    else:
                        title = f"Episode {episode}"
                        rating = float(match.group(1))
                        votes = match.group(2)
                    
                    return {
                        "title": title,
                        "rating": rating,
                        "votes": votes,
                        "success": True,
                        "method": "load_all"
                    }
        
        return None
    except Exception as e:
        print(f"Error cargando todos los episodios: {e}")
        return None

@app.route('/imdb/<imdb_id>/season/<int:season>/episode/<int:episode>/rating')
def get_episode_rating(imdb_id, season, episode):
    """Obtener rating de episodio específico con múltiples estrategias"""
    
    # Validar ID
    if not validate_imdb_id(imdb_id):
        return jsonify({
            "imdb_id": imdb_id,
            "season": season,
            "episode": episode,
            "rating": None,
            "success": False,
            "error": "IMDb ID inválido"
        }), 400
    
    formatted_id = format_imdb_id(imdb_id)
    
    try:
        # Estrategia 1: Intentar endpoint AJAX con paginación inteligente (mejor para episodios altos)
        ajax_result = try_ajax_episodes(formatted_id, season, episode)
        if ajax_result and ajax_result["success"]:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": ajax_result["rating"],
                "votes": ajax_result["votes"],
                "title": ajax_result["title"],
                "success": True,
                "method": ajax_result["method"],
                "error": None
            })
        
        # Estrategia 2: Cargar todos los episodios de una vez (para casos difíciles)
        load_all_result = try_load_all_episodes(formatted_id, season, episode)
        if load_all_result and load_all_result["success"]:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": load_all_result["rating"],
                "votes": load_all_result["votes"],
                "title": load_all_result["title"],
                "success": True,
                "method": load_all_result["method"],
                "error": None
            })
        
        # Estrategia 3: Método original (fallback para episodios tempranos)
        url = f"https://www.imdb.com/title/{formatted_id}/episodes/?season={season}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": None,
                "success": False,
                "error": f"No se pudo acceder a la temporada {season}"
            })
        
        html = response.text
        
        # Buscar el episodio específico
        episode_pattern = rf'S{season}\.E{episode}\s*∙\s*([^<]+)</div>.*?(\d+\.\d+)</span>.*?\(<!-- -->(\d+)<!-- -->\)'
        
        match = re.search(episode_pattern, html, re.DOTALL)
        if match:
            title = match.group(1).strip()
            rating = float(match.group(2))
            votes = match.group(3)
            
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": rating,
                "votes": votes,
                "title": title,
                "success": True,
                "method": "original",
                "error": None
            })
        else:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": None,
                "success": False,
                "error": f"No se encontró el episodio {episode} de {formatted_id}"
            })
            
    except Exception as e:
        return jsonify({
            "imdb_id": formatted_id,
            "season": season,
            "episode": episode,
            "rating": None,
            "success": False,
            "error": f"Error interno: {str(e)}"
        }), 500

# Para Vercel - esto es clave para que funcione
app = app
