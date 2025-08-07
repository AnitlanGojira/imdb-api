# IMDb API Local - Vercel

API Flask para obtener ratings de IMDb desplegada en Vercel. Diseñada específicamente para el workflow N8N del Top Semanal de AniTlan.

## Endpoints

- `GET /` - Información de la API
- `GET /health` - Health check
- `GET /info` - Información detallada del servicio
- `GET /imdb/{imdb_id}/rating` - Rating general de una serie
- `GET /imdb/{imdb_id}/season/{season}/episode/{episode}/rating` - Rating de episodio específico

## Ejemplos de Uso

```bash
# Health check
curl https://tu-api.vercel.app/health

# Rating de serie
curl https://tu-api.vercel.app/imdb/tt0434665/rating

# Rating de episodio específico
curl https://tu-api.vercel.app/imdb/tt0434665/season/1/episode/5/rating
```

## Deployment en Vercel

1. Hacer push a GitHub
2. Importar proyecto en Vercel
3. Deploy automático

## Estructura

- `app.py` - Aplicación Flask principal
- `vercel.json` - Configuración de Vercel
- `requirements.txt` - Dependencias de Python