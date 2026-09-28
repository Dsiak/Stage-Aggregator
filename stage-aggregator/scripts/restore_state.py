"""Restaure uniquement notre base depuis un artefact du dépôt courant."""
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import zipfile


def gh_api(endpoint):
    return subprocess.run(["gh", "api", endpoint], check=True, capture_output=True).stdout


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["DEFAULT_BRANCH"]
    result = json.loads(gh_api(f"repos/{repo}/actions/artifacts?name=aggregator-state&per_page=100"))
    candidates = [item for item in result["artifacts"] if not item["expired"]
                  and item.get("workflow_run", {}).get("head_branch") == branch]
    if not candidates:
        if os.getenv("INITIALIZE_STATE") != "true":
            raise RuntimeError("État manquant : initialisation manuelle requise, ne pas repartir silencieusement de zéro")
        print("Premier démarrage autorisé avec état vide")
        return
    newest = max(candidates, key=lambda item: item["id"])
    data = gh_api(f"repos/{repo}/actions/artifacts/{newest['id']}/zip")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        # Aucun extractall : impossible d'écrire un fichier hors du dossier state.
        info = archive.getinfo("aggregator.db")
        if info.file_size > 100_000_000:
            raise ValueError("Artefact trop volumineux")
        content = archive.read(info)
    path = Path("state/aggregator.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    with sqlite3.connect(path) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("État SQLite invalide")
        db.execute("SELECT fingerprint FROM offers LIMIT 1")
    print("État restauré")


if __name__ == "__main__":
    main()
