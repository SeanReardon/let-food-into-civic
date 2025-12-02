# let-food-into-civic

A funny little Python service running on homelab-infra.

## Development Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally
python -m src.main
```

## Docker

### Build locally

```bash
docker build -t let-food-into-civic .
```

### Run locally

```bash
docker run --rm let-food-into-civic
```

### Using docker-compose

```bash
docker-compose up -d
```

## CI/CD

This project uses GitHub Actions to automatically build and push Docker images to GHCR (GitHub Container Registry).

- **Triggers**: Push to `main`/`master`, tags (`v*`), PRs, or manual dispatch
- **Image**: `ghcr.io/seanreardon/let-food-into-civic`

### Tags

- `latest` - Latest from default branch
- `<branch>` - Branch name
- `<sha>` - Git commit SHA
- `<version>` - Semantic version from tags (e.g., `v1.2.3` → `1.2.3`, `1.2`, `1`)

## Homelab Deployment

Pull on homelab (after setting up service user):

```bash
sudo -u let-food-into-civic git init /home/let-food-into-civic
sudo -u let-food-into-civic git -C /home/let-food-into-civic remote add origin https://github.com/SeanReardon/let-food-into-civic
sudo -u let-food-into-civic git -C /home/let-food-into-civic config core.sparseCheckout true
sudo -u let-food-into-civic bash -c 'echo "docker-compose.yml" > /home/let-food-into-civic/.git/info/sparse-checkout'
sudo -u let-food-into-civic git -C /home/let-food-into-civic pull origin master
```
