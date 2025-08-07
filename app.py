"""
API Local IMDb usando Flask para deployment en Vercel
Optimizada para N8N - Top Semanal AniTlan
"""

from flask import Flask, jsonify
import requests
import re
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app Flask
app = Flask(__name__)

def get_imdb_data(imdb_id):
    """Scraper personalizado de IMDb usando regex"""
    try:
        url = f"https://www.imdb.com/title/{imdb_id}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        html = response.text
        
        # Extraer rating usando regex
        rating = None
        
        # Patrón 1: JSON-LD data
        rating_match = re.search(r'"ratingValue":"?(\d+\.?\d*)"?', html)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except:
                pass
        
        # Patrón 2: Meta tags
        if not rating:
            rating_match = re.search(r'property="v:average">(\d+\.?\d*)', html)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        # Extraer nombre usando regex
        title = None
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            title = title_match.group(1).strip()
            title = re.sub(r'\s*-\s*IMDb.*$', '', title)
        
        return {
            'rating': rating,
            'title': title,
            'success': rating is not None
        }
        
    except Exception as e:
        logger.error(f"Error scraping {imdb_id}: {e}")
        return None

def validate_imdb_id(imdb_id):
    """Validar formato de IMDb ID"""
    if not imdb_id or len(imdb_id) < 7:
        return False
    return True

def format_imdb_id(imdb_id):
    """Formatear IMDb ID"""
    if not imdb_id.startswith('tt'):
        imdb_id = f"tt{imdb_id}"
    return imdb_id

@app.route('/')
def root():
    """Información básica de la API"""
    return jsonify({
        "name": "IMDb API Local - Vercel",
        "version": "1.0.0",
        "status": "running",
        "platform": "vercel",
        "scraper": "available",
        "endpoints": [
            "GET /health",
            "GET /imdb/<imdb_id>/rating",
            "GET /imdb/<imdb_id>/season/<season>/episode/<episode>/rating",
            "GET /info"
        ]
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "platform": "vercel",
        "scraper": "available"
    })

@app.route('/info')
def info():
    """Información del servicio"""
    return jsonify({
        "service": "IMDb API Local - Vercel",
        "version": "1.0.0",
        "description": "API local para obtener ratings de IMDb",
        "usage": "Diseñada para N8N Top Semanal",
        "platform": "vercel",
        "examples": [
            "GET /imdb/tt0434665/rating",
            "GET /imdb/tt0434665/season/1/episode/5/rating"
        ]
    })

@app.route('/imdb/<imdb_id>/rating')
def get_rating(imdb_id):
    """Obtener rating de serie completa"""
    
    # Validar ID
    if not validate_imdb_id(imdb_id):
        return jsonify({
            "imdb_id": imdb_id,
            "rating": None,
            "success": False,
            "error": "IMDb ID inválido"
        }), 400
    
    # Formatear ID
    formatted_id = format_imdb_id(imdb_id)
    logger.info(f"🔍 Obteniendo rating de serie para: {formatted_id}")
    
    try:
        # Obtener datos
        result = get_imdb_data(formatted_id)
        
        if not result:
            return jsonify({
                "imdb_id": formatted_id,
                "rating": None,
                "success": False,
                "error": "No se encontró información"
            })
        
        logger.info(f"✅ Rating obtenido: {result['rating']}")
        
        return jsonify({
            "imdb_id": formatted_id,
            "rating": result['rating'],
            "title": result['title'],
            "success": result['success'],
            "error": None if result['success'] else "No se encontró rating"
        })
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return jsonify({
            "imdb_id": formatted_id,
            "rating": None,
            "success": False,
            "error": f"Error interno: {str(e)}"
        }), 500

@app.route('/imdb/<imdb_id>/season/<int:season>/episode/<int:episode>/rating')
def get_episode_rating(imdb_id, season, episode):
    """Obtener rating de episodio específico - ENDPOINT PRINCIPAL PARA N8N"""
    
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
    logger.info(f"🔍 Obteniendo rating S{season}.E{episode} para: {formatted_id}")
    
    try:
        # URL de episodios de la temporada específica
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
        
        # Buscar el episodio específico: S{season}.E{episode} ∙ Title
        # Patrón basado en el HTML real de IMDb con comentarios <!-- -->
        episode_pattern = rf'S{season}\.E{episode}\s*∙\s*([^<]+)</div>.*?(\d+\.\d+)</span>.*?\(<!-- -->(\d+)<!-- -->\)'
        
        match = re.search(episode_pattern, html, re.DOTALL)
        if match:
            title = match.group(1).strip()
            rating = float(match.group(2))
            votes = match.group(3)
            
            logger.info(f"✅ Rating episodio encontrado: {rating}")
            
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": rating,
                "votes": votes,
                "title": title,
                "success": True,
                "error": None
            })
        else:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": None,
                "success": False,
                "error": f"No se encontró el episodio S{season}.E{episode}"
            })
            
    except Exception as e:
        logger.error(f"❌ Error obteniendo episodio: {e}")
        return jsonify({
            "imdb_id": formatted_id,
            "season": season,
            "episode": episode,
            "rating": None,
            "success": False,
            "error": f"Error interno: {str(e)}"
        }), 500

# Para compatibilidad con Vercel
def handler(request):
    """Handler para Vercel"""
    return app(request.environ, lambda *args: None)

if __name__ == "__main__":
    # Para desarrollo local
    port = 8001
    print(f"🚀 Iniciando API Flask en http://127.0.0.1:{port}")
    print(f"🔍 Health check: http://127.0.0.1:{port}/health")
    print(f"🎬 Test Bleach: http://127.0.0.1:{port}/imdb/tt0434665/rating")
    print("📝 Presiona Ctrl+C para detener")
    print("=" * 50)
    
    try:
        app.run(
            host='127.0.0.1',
            port=port,
            debug=False,
            threaded=True
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        input("Presiona Enter para continuar...")