from flask import Flask, jsonify, request
import requests
import re
import json
import os

app = Flask(__name__)

# Configuración OMDb
# Leer desde variable de entorno para no exponer la key en repos públicos
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
OMDB_BASE_URL = "http://www.omdbapi.com"
# Cabeceras por defecto para IMDb y timeout seguro (connect, read)
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}
REQUEST_TIMEOUT = (4, 8)

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
            "GET /imdb/<imdb_id>/season/<season>/episode/<episode>/rating",
            "GET /imdb/<episode_id>/rating"
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

def get_episode_id_from_omdb(imdb_id, season, episode):
    """Obtener episode ID específico de OMDb (fallback cuando no se encuentra en lista)"""
    try:
        # Si no hay key configurada, no intentar OMDb
        if not OMDB_API_KEY:
            app.logger.warning("OMDb API key missing. Skipping OMDb lookup.")
            return {"success": False}
        omdb_url = f"{OMDB_BASE_URL}?i={imdb_id}&Season={season}&Episode={episode}&apikey={OMDB_API_KEY}"
        
        response = requests.get(omdb_url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            
            if data.get("Response") == "True" and data.get("imdbID"):
                return {
                    "success": True,
                    "episode_id": data["imdbID"],
                    "title": data.get("Title", f"Episode {episode}"),
                    "method": "omdb_episode_id"
                }
        
        return {"success": False}
    except Exception as e:
        print(f"Error en OMDb: {e}")
        return {"success": False}


@app.route('/imdb/<imdb_id>/season/<int:season>/episode/<int:episode>/rating')
def get_episode_rating(imdb_id, season, episode):
    """Obtener rating de episodio específico"""
    
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
        # URL de episodios de la temporada específica
        url = f"https://www.imdb.com/title/{formatted_id}/episodes/?season={season}"
        app.logger.info(f"GET season list: {formatted_id} S{season}E{episode}")
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
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
        
        # Buscar el episodio específico anclando al enlace del episodio en la lista
        # Enlaces de episodios usan el patrón ref_=ttep_ep_{episode}
        # Después del enlace, aparecen: rating -> maxRating(10) -> voteCount
        block_pattern = rf'ref_=ttep_ep_{episode}.*?ipc-rating-star--rating">(\d+\.\d+)</span>.*?ipc-rating-star--maxRating">.*?</span>.*?ipc-rating-star--voteCount">([^<]+)</span>'
        block_match = re.search(block_pattern, html, re.DOTALL)
        if block_match:
            rating = float(block_match.group(1))
            votes_raw = block_match.group(2)
            # Limpia el texto de votos: elimina espacios/nbsp y comentarios, deja por ejemplo "9.8k" o "12,345"
            votes = re.sub(r'\s|&nbsp;|\(|\)', '', votes_raw)
            votes = re.sub(r'<!--.*?-->', '', votes)
            votes = votes.strip()

            # Intenta obtener el título a partir del mismo anchor ref_=ttep_ep_{episode}
            title_match = re.search(rf'ref_=ttep_ep_{episode}[^>]*>\s*(?:S{season}\.E{episode}\s*[^<]*?∙\s*)?([^<]+)\s*</a>', html, re.DOTALL)
            title = title_match.group(1).strip() if title_match else f"Episode {episode}"
            app.logger.info("method=direct_scraping status=success")
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": rating,
                "votes": votes,
                "title": title,
                "success": True,
                "method": "direct_scraping",
                "error": None
            })
        
        # Si no encuentra con rating, buscar solo el episodio para obtener episode_id
        episode_basic_pattern = rf'S{season}\.E{episode}\s*∙\s*([^<\]]+)'
        match = re.search(episode_basic_pattern, html, re.DOTALL)
        if match:
            title = match.group(1).strip()
            
            # Buscar el episode_id en el HTML
            episode_id_pattern = rf'S{season}\.E{episode}.*?title/(tt\d+)/\?'
            episode_id_match = re.search(episode_id_pattern, html)
            
            if episode_id_match:
                episode_id = episode_id_match.group(1)
                app.logger.info(f"method=episode_id_found_in_list episode_id={episode_id}")
                return jsonify({
                    "imdb_id": formatted_id,
                    "season": season,
                    "episode": episode,
                    "rating": None,
                    "success": False,
                    "method": "episode_id_found_in_list",
                    "episode_id": episode_id,
                    "title": title,
                    "error": f"Episode ID encontrado: {episode_id}. Use endpoint /imdb/{episode_id}/rating para obtener rating."
                })
        else:
            # Si no se encuentra en la lista, usar OMDb como fallback
            omdb_result = get_episode_id_from_omdb(formatted_id, season, episode)
            if omdb_result and omdb_result["success"]:
                app.logger.info(f"method=omdb_episode_id_found episode_id={omdb_result['episode_id']}")
                return jsonify({
                    "imdb_id": formatted_id,
                    "season": season,
                    "episode": episode,
                    "rating": None,
                    "success": False,
                    "method": "omdb_episode_id_found",
                    "episode_id": omdb_result["episode_id"],
                    "title": omdb_result["title"],
                    "error": f"Episode ID encontrado: {omdb_result['episode_id']}. Use endpoint /imdb/{omdb_result['episode_id']}/rating para obtener rating."
                })
            else:
                return jsonify({
                    "imdb_id": formatted_id,
                    "season": season,
                    "episode": episode,
                    "rating": None,
                    "success": False,
                    "error": f"No se encontró el episodio {episode} (S{season}.E{episode})" if formatted_id != "tt0388629" else f"No se encontró el episodio {episode} de One Piece"
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

@app.route('/imdb/<episode_id>/rating')
def get_individual_episode_rating(episode_id):
    """Obtener rating de un episodio específico usando su IMDb ID individual"""
    
    # Validar ID
    if not validate_imdb_id(episode_id):
        return jsonify({
            "episode_id": episode_id,
            "rating": None,
            "success": False,
            "error": "Episode ID inválido"
        }), 400
    
    formatted_id = format_imdb_id(episode_id)
    
    try:
        # Hacer scraping directo de la página del episodio específico
        episode_url = f"https://www.imdb.com/title/{formatted_id}/"
        app.logger.info(f"GET episode page: {formatted_id}")
        response = requests.get(episode_url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return jsonify({
                "episode_id": formatted_id,
                "rating": None,
                "success": False,
                "error": f"No se pudo acceder a la página del episodio {formatted_id}"
            })
        
        html = response.text
        # Primero, intentar extraer desde JSON-LD (más estable y rápido)
        try:
            ld_matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL)
            for ld in ld_matches:
                ld = ld.strip()
                if not ld:
                    continue
                try:
                    data = json.loads(ld)
                except Exception:
                    continue
                # Puede ser un objeto o una lista de objetos
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    agg = item.get("aggregateRating") or {}
                    if not agg:
                        continue
                    rv = agg.get("ratingValue")
                    rc = agg.get("ratingCount")
                    if rv is None:
                        continue
                    try:
                        rating = float(rv)
                    except Exception:
                        continue
                    votes = str(rc) if rc is not None else "0"
                    title = item.get("name") or "Episode"
                    app.logger.info("method=individual_episode_scraping source=jsonld status=success")
                    return jsonify({
                        "episode_id": formatted_id,
                        "rating": rating,
                        "votes": votes,
                        "title": title,
                        "success": True,
                        "method": "individual_episode_scraping",
                        "error": None
                    })
        except Exception:
            pass

        # Buscar rating en la página del episodio específico
        rating_patterns = [
            r'"ratingValue":(\d+\.\d+)',
            r'ratingValue"[^>]*>(\d+\.\d+)',
            r'(\d+\.\d+)</span>.*?based on.*?(\d+).*?user rating',
            r'(\d+\.\d+)/10.*?(\d+).*?user ratings'
        ]
        
        for pattern in rating_patterns:
            rating_match = re.search(pattern, html, re.DOTALL)
            if rating_match:
                rating = float(rating_match.group(1))
                
                # Buscar votos
                votes_patterns = [
                    r'"ratingCount":(\d+)',
                    r'ratingCount"[^>]*>(\d+)',
                    r'based on.*?(\d+).*?user rating',
                    r'(\d+).*?user ratings'
                ]
                
                votes = "0"
                for votes_pattern in votes_patterns:
                    votes_match = re.search(votes_pattern, html, re.DOTALL)
                    if votes_match:
                        votes = votes_match.group(1)
                        break
                
                # Buscar título del episodio
                title_patterns = [
                    r'<h1[^>]*>([^<]+)</h1>',
                    r'"name":"([^"]+)"',
                    r'<title>([^<]+)</title>'
                ]
                
                title = "Episode"
                for title_pattern in title_patterns:
                    title_match = re.search(title_pattern, html, re.DOTALL)
                    if title_match:
                        title = title_match.group(1).strip()
                        break
                
                return jsonify({
                    "episode_id": formatted_id,
                    "rating": rating,
                    "votes": votes,
                    "title": title,
                    "success": True,
                    "method": "individual_episode_scraping",
                    "error": None
                })
        
        return jsonify({
            "episode_id": formatted_id,
            "rating": None,
            "success": False,
            "error": f"No se encontró rating en la página del episodio {formatted_id}"
        })
        
    except Exception as e:
        return jsonify({
            "episode_id": formatted_id,
            "rating": None,
            "success": False,
            "error": f"Error interno: {str(e)}"
        }), 500

# Para Vercel - esto es clave para que funcione
if __name__ == "__main__":
    app.run(debug=False)
