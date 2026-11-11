# Niveau 3 — Déploiement continu

## Ce que fait `cd.yml`

| Job | Rôle |
|---|---|
| `build` | construit l'image (`Dockerfile`) et la pousse sur `ghcr.io/<owner>/<repo>:<sha>` et `:latest` |
| `smoke-test` | lance la stack `prod` complète sur le runner, dépose les CSV dans le S3 et attend que le **worker** les traite seul, puis vérifie la base (`tests/e2e`) et la santé du dashboard |
| `deploy-vm` | si les secrets existent : copie `docker-compose.yml` sur la VM et lance `docker compose --profile prod up -d` avec la nouvelle image |

Déclenchement : automatiquement après une CI réussie sur `main`, ou manuellement.

## Stack de production

| Service | Image | Port | Rôle |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5433 | base de données |
| `s3` | `chrislusf/seaweedfs:4.50` | 8333 | S3 local |
| `worker` | image de l'app | — | `txpipeline schedule` : traite les nouveaux fichiers toutes les `SCHEDULE_INTERVAL` s |
| `dashboard` | image de l'app | 8501 | Streamlit |

Le worker est sans état : il peut redémarrer à tout moment, le registre
`processed_files` garantit qu'aucun fichier n'est retraité.

## Préparer une VM (Ubuntu)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER          # puis se reconnecter
mkdir -p ~/txpipeline && cd ~/txpipeline
# créer ~/txpipeline/.env avec des mots de passe forts (voir .env.example)
```

Secrets GitHub à créer (Settings → Secrets and variables → Actions) :

| Secret | Valeur |
|---|---|
| `DEPLOY_HOST` | IP ou nom DNS de la VM |
| `DEPLOY_USER` | utilisateur SSH |
| `DEPLOY_SSH_KEY` | clé privée SSH (la clé publique dans `~/.ssh/authorized_keys` de la VM) |

Si l'image GHCR est privée, la VM s'authentifie avec le jeton du workflow à chaque
déploiement ; pour des `pull` ultérieurs hors CD, rendre le package public ou faire un
`docker login ghcr.io` avec un PAT `read:packages`.

## Tester la stack de prod en local

```bash
docker compose --profile prod up -d --build --wait
python -m txpipeline generate && python -m txpipeline upload
docker compose logs -f worker          # "3 traité(s)" au cycle suivant
# http://localhost:8501
docker compose --profile prod down     # (-v pour supprimer les données)
```
