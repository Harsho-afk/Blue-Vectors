"""
ARIA — Graph Assembly endpoint
GET /api/cases/{case_id}/graph   → { nodes[], edges[] }

Assembles a unified investigation graph from:
- case_identifiers (seed nodes)
- accounts (profile nodes)
- linkage_results (correlation edges)
- insights/cross_reference (hard link edges)
- posts with metadata.type='network' (GitHub follower/following edges)
- osint_lookups/maigret (discovery edges)
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from auth import get_current_user, get_db_conn

router = APIRouter(prefix="/api/cases", tags=["graph"])


def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if row["investigator_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


def _parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val or {}


def _num(val):
    """Convert Decimal/numeric DB values to plain int or float for JSON."""
    if val is None:
        return None
    return float(val)


@router.get("/{case_id}/graph")
def get_case_graph(case_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()

        nodes = []
        edges = []
        node_ids = set()

        # ─── 1. Seed Identifier Nodes ────────────────────────────────────────
        cur.execute(
            "SELECT id, identifier_type, value, platform_hint FROM case_identifiers WHERE case_id = %s",
            (case_id,),
        )
        seeds = [dict(r) for r in cur.fetchall()]
        for s in seeds:
            nid = f"seed:{s['id']}"
            nodes.append({
                "id": nid,
                "type": "seed",
                "label": s["value"],
                "identifier_type": s["identifier_type"],
                "platform": s["platform_hint"],
                "size": 14,
            })
            node_ids.add(nid)

        # ─── 2. Account Nodes ────────────────────────────────────────────────
        cur.execute(
            """SELECT id, platform, username, display_name, bio, location,
                      profile_image_url, follower_count, following_count, karma
               FROM accounts WHERE case_id = %s""",
            (case_id,),
        )
        accounts = [dict(r) for r in cur.fetchall()]
        account_map = {}
        for a in accounts:
            nid = f"account:{a['id']}"
            account_map[a["id"]] = a
            nodes.append({
                "id": nid,
                "type": "account",
                "label": a["username"],
                "platform": a["platform"],
                "display_name": a["display_name"],
                "bio": a["bio"],
                "location": a["location"],
                "avatar": a["profile_image_url"],
                "follower_count": _num(a["follower_count"]),
                "following_count": _num(a["following_count"]),
                "size": 10,
            })
            node_ids.add(nid)

        # Connect seeds to their discovered accounts (by matching value to username/platform)
        for s in seeds:
            seed_nid = f"seed:{s['id']}"
            for a in accounts:
                match = False
                if s["identifier_type"] == "username":
                    if s["value"].lower() == a["username"].lower():
                        if s["platform_hint"] is None or s["platform_hint"] == a["platform"]:
                            match = True
                elif s["identifier_type"] == "profile_url":
                    if a["username"].lower() in s["value"].lower():
                        match = True
                if match:
                    edges.append({
                        "source": seed_nid,
                        "target": f"account:{a['id']}",
                        "type": "seed_to_account",
                        "label": "discovered",
                        "confidence": 1.0,
                        "evidence_class": "deterministic",
                    })

        # ─── 3. Correlation Edges ────────────────────────────────────────────
        cur.execute(
            """SELECT id, account_a_id, account_b_id, confidence, shap_json
               FROM linkage_results WHERE case_id = %s""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            shap = _parse_json(r["shap_json"])
            confidence = float(r["confidence"] or 0)
            band = shap.get("band", "Low")
            evidence_type = shap.get("evidence_type", "circumstantial_convergence")
            tier1 = shap.get("tier1_links", [])

            edges.append({
                "source": f"account:{r['account_a_id']}",
                "target": f"account:{r['account_b_id']}",
                "type": "correlation",
                "label": f"{confidence:.0f}% ({band})",
                "confidence": confidence / 100,
                "band": band,
                "evidence_type": evidence_type,
                "evidence_class": "hard_link" if evidence_type == "hard_link" else "probabilistic",
                "shap": shap,
                "tier1_links": tier1,
            })

        # ─── 4. Cross-Reference Edges (from insights) ────────────────────────
        cur.execute(
            """SELECT id, account_id, claim, confidence, evidence
               FROM insights
               WHERE case_id = %s AND category = 'cross_reference'""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            evidence = _parse_json(r.get("evidence"))
            if not r["account_id"]:
                continue

            source_nid = f"account:{r['account_id']}"
            target_nid = None
            link_detail = r["claim"]

            # Try to find the target account from the claim
            if isinstance(evidence, list):
                for ev in evidence:
                    detail = ev.get("detail", "")
                    # Look for platform/handle references in evidence
                    for a in accounts:
                        if a["id"] == r["account_id"]:
                            continue
                        if a["username"].lower() in detail.lower() or a["platform"].lower() in detail.lower():
                            target_nid = f"account:{a['id']}"
                            break
                    if target_nid:
                        break

            if target_nid and source_nid != target_nid:
                edges.append({
                    "source": source_nid,
                    "target": target_nid,
                    "type": "cross_reference",
                    "label": "bio link",
                    "confidence": 0.95,
                    "evidence_class": "hard_link",
                    "detail": link_detail,
                })

        # ─── 5. Network Edges (GitHub + Twitter + Instagram) ────────────────
        # All platforms store followers/following as synthetic posts with
        # metadata.type='network', metadata.direction, metadata.logins[]
        all_account_ids = [a["id"] for a in accounts]
        # Map platform:username_lower -> account_id for cross-matching
        platform_username_map = {}
        for a in accounts:
            platform_username_map[(a["platform"], a["username"].lower())] = a["id"]

        # Track follower/following sets per account for mutual computation
        followers_of = {}   # account_id -> set of logins
        following_of = {}   # account_id -> set of logins
        account_platform = {a["id"]: a["platform"] for a in accounts}

        if all_account_ids:
            placeholders = ",".join(["%s"] * len(all_account_ids))
            cur.execute(
                f"""SELECT account_id, metadata FROM posts
                    WHERE account_id IN ({placeholders})
                    AND metadata->>'type' = 'network'""",
                tuple(all_account_ids),
            )
            seen_network_edges = set()
            for row in cur.fetchall():
                r = dict(row)
                meta = _parse_json(r["metadata"])
                direction = meta.get("direction", "")
                logins = meta.get("logins", [])
                source_aid = r["account_id"]
                source_nid = f"account:{source_aid}"
                platform = account_platform.get(source_aid, "")

                # Store for mutual computation
                login_set = {l.lower() for l in logins}
                if direction == "followers":
                    followers_of[source_aid] = login_set
                elif direction == "following":
                    following_of[source_aid] = login_set

                # Create edges to other collected accounts on the same platform
                for login in logins:
                    login_lower = login.lower()
                    target_aid = platform_username_map.get((platform, login_lower))
                    if not target_aid or target_aid == source_aid:
                        continue
                    edge_key = (source_aid, target_aid, direction)
                    if edge_key in seen_network_edges:
                        continue
                    seen_network_edges.add(edge_key)

                    edge_label = "follows" if direction == "following" else "followed by"
                    edges.append({
                        "source": source_nid,
                        "target": f"account:{target_aid}",
                        "type": "network",
                        "label": edge_label,
                        "confidence": 1.0,
                        "evidence_class": "network",
                        "platform": platform,
                    })

        # ─── 5b. Mutual followers between accounts on same platform ──────
        # For each pair of accounts on the same platform, compute shared followers
        from itertools import combinations
        platform_groups = {}
        for a in accounts:
            platform_groups.setdefault(a["platform"], []).append(a["id"])

        for plat, aids in platform_groups.items():
            if len(aids) < 2:
                continue
            for aid_a, aid_b in combinations(aids, 2):
                followers_a = followers_of.get(aid_a, set())
                followers_b = followers_of.get(aid_b, set())
                following_a = following_of.get(aid_a, set())
                following_b = following_of.get(aid_b, set())

                # Shared followers = people who follow both
                shared_followers = followers_a & followers_b
                # Shared following = people both accounts follow
                shared_following = following_a & following_b
                total_shared = shared_followers | shared_following

                if len(total_shared) >= 2:
                    union_followers = followers_a | followers_b
                    union_following = following_a | following_b
                    union_total = union_followers | union_following
                    jaccard = len(total_shared) / len(union_total) if union_total else 0

                    mutual_list = sorted(total_shared)[:50]
                    edges.append({
                        "source": f"account:{aid_a}",
                        "target": f"account:{aid_b}",
                        "type": "mutual_network",
                        "label": f"{len(total_shared)} mutual connections",
                        "confidence": min(0.95, 0.3 + jaccard * 2),
                        "evidence_class": "network",
                        "platform": plat,
                        "detail": (
                            f"{len(shared_followers)} shared followers, "
                            f"{len(shared_following)} shared following "
                            f"(Jaccard: {jaccard:.2f})"
                        ),
                        "shared_count": len(total_shared),
                        "jaccard": round(jaccard, 3),
                        "mutual_usernames": mutual_list,
                    })

        # ─── 6. Maigret Discovery Nodes ──────────────────────────────────────
        cur.execute(
            """SELECT id, input_value, result_json FROM osint_lookups
               WHERE case_id = %s AND lookup_type = 'maigret'""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            result = _parse_json(r["result_json"])
            categories = result.get("categories", {})

            # Find the seed/account this lookup originated from
            origin_nid = None
            input_val = r["input_value"].lower()
            for s in seeds:
                if s["value"].lower() == input_val:
                    origin_nid = f"seed:{s['id']}"
                    break
            if not origin_nid:
                for a in accounts:
                    if a["username"].lower() == input_val:
                        origin_nid = f"account:{a['id']}"
                        break

            # Create discovery nodes for platforms not already collected
            collected_platforms = {(a["platform"], a["username"].lower()) for a in accounts}
            discovery_count = 0
            max_discoveries = 15  # limit to avoid graph explosion

            for cat_name, platforms in categories.items():
                if not isinstance(platforms, list):
                    continue
                for p in platforms:
                    if discovery_count >= max_discoveries:
                        break
                    platform_name = p.get("platform", "").lower().replace(" ", "_")
                    url = p.get("url", "")
                    parsed = p.get("parsed_data") or {}
                    username_found = parsed.get("username", "") or "" if isinstance(parsed, dict) else ""

                    # Skip if already collected as a full account
                    if (platform_name, username_found.lower()) in collected_platforms:
                        continue
                    if not url:
                        continue

                    disc_nid = f"discovery:{r['id']}:{platform_name}"
                    if disc_nid in node_ids:
                        continue

                    nodes.append({
                        "id": disc_nid,
                        "type": "discovery",
                        "label": username_found or platform_name,
                        "platform": platform_name,
                        "url": url,
                        "category": cat_name,
                        "size": 6,
                    })
                    node_ids.add(disc_nid)
                    discovery_count += 1

                    if origin_nid:
                        edges.append({
                            "source": origin_nid,
                            "target": disc_nid,
                            "type": "discovery",
                            "label": "username found",
                            "confidence": 0.3,
                            "evidence_class": "discovery",
                        })

            # linked_accounts from Maigret
            linked = result.get("linked_accounts", [])
            for la in linked:
                la_username = la.get("username", "").lower()
                la_platform = la.get("source_platform", "").lower()
                # Check if this linked account is already collected
                for a in accounts:
                    if a["username"].lower() == la_username:
                        if origin_nid:
                            edges.append({
                                "source": origin_nid,
                                "target": f"account:{a['id']}",
                                "type": "cross_reference",
                                "label": f"linked ({la.get('how_found', 'maigret')})",
                                "confidence": 0.8,
                                "evidence_class": "hard_link",
                            })
                        break

        # ─── 7. Coordination Edges (from insights) ───────────────────────────
        cur.execute(
            """SELECT id, claim, confidence, evidence
               FROM insights
               WHERE case_id = %s AND category = 'coordination'""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            evidence = _parse_json(r.get("evidence"))
            # Coordination insights often reference account pairs in evidence
            if isinstance(evidence, list):
                involved_accounts = set()
                for ev in evidence:
                    src_id = ev.get("source_id")
                    if src_id and ev.get("source_table") == "accounts":
                        involved_accounts.add(src_id)
                involved = list(involved_accounts)
                for i in range(len(involved)):
                    for j in range(i + 1, len(involved)):
                        edges.append({
                            "source": f"account:{involved[i]}",
                            "target": f"account:{involved[j]}",
                            "type": "coordination",
                            "label": "coordinated behavior",
                            "confidence": 0.5,
                            "evidence_class": "behavioral",
                            "detail": r["claim"],
                        })

        # ─── 8. Compute graph stats ──────────────────────────────────────────
        stats = {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "seeds": len(seeds),
            "accounts": len(accounts),
            "discoveries": sum(1 for n in nodes if n["type"] == "discovery"),
            "hard_links": sum(1 for e in edges if e.get("evidence_class") == "hard_link"),
            "correlations": sum(1 for e in edges if e["type"] == "correlation"),
            "network_edges": sum(1 for e in edges if e["type"] == "network"),
            "mutual_connections": sum(1 for e in edges if e["type"] == "mutual_network"),
            "mutual_total_shared": sum(e.get("shared_count", 0) for e in edges if e["type"] == "mutual_network"),
        }

    finally:
        conn.close()

    return {"nodes": nodes, "edges": edges, "stats": stats}
