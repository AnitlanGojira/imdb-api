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

def scrape_individual_episode(episode_id):
    """Scrapea la página individual del episodio para obtener rating, votos y título."""
    formatted_id = format_imdb_id(episode_id)
    try:
        episode_url = f"https://www.imdb.com/title/{formatted_id}/"
        response = requests.get(episode_url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "error": f"No se pudo acceder a la página del episodio {formatted_id}"}

        html = response.text

        # 1) Intentar JSON-LD (más estable)
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
                    return {
                        "success": True,
                        "episode_id": formatted_id,
                        "rating": rating,
                        "votes": votes,
                        "title": title,
                        "method": "individual_episode_scraping"
                    }
        except Exception:
            pass

        # 2) Patrones alternativos en HTML
        rating_patterns = [
            r'"ratingValue":\s*(\d+(?:\.\d+)?)',
            r'aria-label="IMDb rating:\s*(\d+(?:\.\d+)?)/10"',
            r'ipc-rating-star--rating">(\d+(?:\.\d+)?)<',
            r'data-testid="ratingGroup--imdb-rating"[^>]*?>\s*<span[^>]*?>(\d+(?:\.\d+)?)<'
        ]

        votes_patterns = [
            r'"ratingCount":\s*(\d+)',
            r'ipc-rating-star--voteCount">([^<]+)<',
            r'(\d[\d,\.Kk]+)\s+ratings',
            r'based on\s*(\d[\d,\.Kk]+)\s*user ratings'
        ]

        rating = None
        for pattern in rating_patterns:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    rating = float(m.group(1))
                    break
                except Exception:
                    continue

        if rating is None:
            return {"success": False, "error": f"No se encontró rating en la página del episodio {formatted_id}"}

        votes = "0"
        for vpat in votes_patterns:
            vm = re.search(vpat, html, re.DOTALL)
            if vm:
                votes = vm.group(1)
                break
        # Asegurar valor por defecto cuando no se detecten votos
        if not votes or not str(votes).strip():
            votes = "0"

        # Título
        title_patterns = [
            r'<h1[^>]*>([^<]+)</h1>',
            r'"name":"([^"]+)"',
            r'<title>([^<]+)</title>'
        ]
        title = "Episode"
        for tpat in title_patterns:
            tm = re.search(tpat, html, re.DOTALL)
            if tm:
                title = tm.group(1).strip()
                break

        return {
            "success": True,
            "episode_id": formatted_id,
            "rating": rating,
            "votes": votes,
            "title": title,
            "method": "individual_episode_scraping"
        }
    except Exception as e:
        return {"success": False, "error": f"Error interno: {str(e)}"}

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

        # 1) Localizar el anchor del episodio por ref_=ttep_ep_{episode} y extraer episode_id
        link_patterns = [
            rf'href="(?:https?://www\.imdb\.com)?/title/(tt\d+)/\?ref_=ttep_ep_{episode}"',
            rf"href='(?:https?://www\.imdb\.com)?/title/(tt\d+)/\?ref_=ttep_ep_{episode}'",
            rf'href="/title/(tt\d+)/\?ref_=ttep_ep_{episode}"'
        ]
        link_match = None
        for lp in link_patterns:
            link_match = re.search(lp, html)
            if link_match:
                break

        if link_match:
            episode_id = link_match.group(1)
            anchor_idx = link_match.start()
            # Tomar un snippet alrededor del anchor para buscar rating/votos
            snippet = html[anchor_idx: anchor_idx + 3000]

            # 2) Extraer rating y votos con varios patrones tolerantes
            rating_patterns = [
                rf'ipc-rating-star--rating">(\d+(?:\.\d+)?)<',
                rf'aria-label="IMDb rating:\s*(\d+(?:\.\d+)?)/10"',
                rf'"ratingValue":\s*(\d+(?:\.\d+)?)',
                rf'data-testid="ratingGroup--imdb-rating"[^>]*?>\s*<span[^>]*?>(\d+(?:\.\d+)?)<'
            ]
            votes_patterns = [
                rf'ipc-rating-star--voteCount">([^<]+)<',
                rf'(\d[\d,\.Kk]+)\s+ratings',
                rf'"ratingCount":\s*(\d+)'
            ]

            rating_val = None
            for rp in rating_patterns:
                rm = re.search(rp, snippet, re.DOTALL)
                if rm:
                    try:
                        rating_val = float(rm.group(1))
                        break
                    except Exception:
                        continue

            if rating_val is not None:
                votes = "0"
                for vp in votes_patterns:
                    vm = re.search(vp, snippet, re.DOTALL)
                    if vm:
                        votes_raw = vm.group(1)
                        # Normalizar
                        votes = re.sub(r'\s|&nbsp;|\(|\)', '', votes_raw)
                        votes = re.sub(r'<!--.*?-->', '', votes)
                        votes = votes.strip()
                        break
                # Asegurar valor por defecto cuando no se detecten votos
                if not votes or not str(votes).strip():
                    votes = "0"

                # Título desde el anchor
                title_match = re.search(rf'ref_=ttep_ep_{episode}[^>]*>\s*(?:S{season}\.E{episode}\s*[^<]*?∙\s*)?([^<]+)\s*</a>', snippet, re.DOTALL)
                title = title_match.group(1).strip() if title_match else f"Episode {episode}"
                app.logger.info("method=direct_scraping status=success")
                return jsonify({
                    "imdb_id": formatted_id,
                    "season": season,
                    "episode": episode,
                    "rating": rating_val,
                    "votes": votes,
                    "title": title,
                    "success": True,
                    "method": "direct_scraping",
                    "error": None
                })

            # 3) Si no encontramos rating en la lista pero sí el episode_id, probar página individual
            fallback = scrape_individual_episode(episode_id)
            if fallback.get("success"):
                app.logger.info("method=individual_episode_fallback status=success")
                return jsonify({
                    "imdb_id": formatted_id,
                    "season": season,
                    "episode": episode,
                    "rating": fallback["rating"],
                    "votes": fallback.get("votes", "0"),
                    "title": fallback.get("title", f"Episode {episode}"),
                    "success": True,
                    "method": "individual_episode_scraping",
                    "episode_id": episode_id,
                    "error": None
                })

            # Si tampoco en la individual, devolver guía para usar endpoint individual (contrato previo)
            app.logger.info(f"method=episode_id_found_in_list episode_id={episode_id}")
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": None,
                "success": False,
                "method": "episode_id_found_in_list",
                "episode_id": episode_id,
                "title": f"Episode {episode}",
                "error": f"Episode ID encontrado: {episode_id}. Use endpoint /imdb/{episode_id}/rating para obtener rating."
            })

        # 4) Si no aparece el episodio en la lista, usar OMDb solo para obtener episode_id
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
                "title": omdb_result.get("title", f"Episode {episode}"),
                "error": f"Episode ID encontrado: {omdb_result['episode_id']}. Use endpoint /imdb/{omdb_result['episode_id']}/rating para obtener rating."
            })
        else:
            return jsonify({
                "imdb_id": formatted_id,
                "season": season,
                "episode": episode,
                "rating": None,
                "success": False,
                "method": "omdb_episode_id_not_found",
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
        app.logger.info(f"GET episode page: {formatted_id}")
        result = scrape_individual_episode(formatted_id)
        if result.get("success"):
            return jsonify({
                "episode_id": result["episode_id"],
                "rating": result["rating"],
                "votes": result.get("votes", "0"),
                "title": result.get("title", "Episode"),
                "success": True,
                "method": result.get("method", "individual_episode_scraping"),
                "error": None
            })
        else:
            return jsonify({
                "episode_id": formatted_id,
                "rating": None,
                "success": False,
                "error": result.get("error", f"No se encontró rating en la página del episodio {formatted_id}")
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
