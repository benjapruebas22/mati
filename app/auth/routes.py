from flask import request, render_template, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3


def register_auth(bp, get_db, ensure_auth_tables, default_redirect_for_role):
    def _safe_ensure_auth(con):
        try:
            ensure_auth_tables(con)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "database is locked" in msg or "database table is locked" in msg:
                row = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'"
                ).fetchone()
                if not row:
                    raise
            else:
                raise

    @bp.route("/login", methods=["GET", "POST"], endpoint="login")
    def login():
        con = get_db()
        _safe_ensure_auth(con)

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()

            row = con.execute("""
                SELECT id, username, full_name, role, password_hash, must_change, activo
                FROM usuarios
                WHERE LOWER(COALESCE(username,'')) = LOWER(?)
            """, (username,)).fetchone()

            if not row or not row["activo"]:
                con.close()
                flash("Usuario o clave invalidos.", "error")
                return render_template("login.html")

            if not check_password_hash(row["password_hash"], password):
                con.close()
                flash("Usuario o clave invalidos.", "error")
                return render_template("login.html")

            session["user_id"] = row["id"]
            session["username"] = row["username"]
            session["full_name"] = row["full_name"]
            session["role"] = row["role"]
            session["must_change"] = 1 if row["must_change"] else 0
            con.close()

            if session.get("must_change"):
                return redirect(url_for("password_change"))

            nxt = request.args.get("next")
            if nxt:
                return redirect(nxt)
            return redirect(default_redirect_for_role(session.get("role")))

        con.close()
        return render_template("login.html")

    @bp.route("/logout", endpoint="logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @bp.route("/password", methods=["GET", "POST"], endpoint="password_change")
    def password_change():
        if not session.get("user_id"):
            return redirect(url_for("login"))

        con = get_db()
        _safe_ensure_auth(con)

        if request.method == "POST":
            current = (request.form.get("current_password") or "").strip()
            new1 = (request.form.get("new_password") or "").strip()
            new2 = (request.form.get("confirm_password") or "").strip()

            row = con.execute("SELECT password_hash FROM usuarios WHERE id = ?", (session.get("user_id"),)).fetchone()
            if not row or not check_password_hash(row["password_hash"], current):
                con.close()
                flash("Clave actual incorrecta.", "error")
                return render_template("password_change.html")

            if not new1 or new1 != new2:
                con.close()
                flash("La nueva clave no coincide.", "error")
                return render_template("password_change.html")

            con.execute("UPDATE usuarios SET password_hash = ?, must_change = 0 WHERE id = ?",
                        (generate_password_hash(new1), session.get("user_id")))
            con.commit()
            con.close()
            session["must_change"] = 0
            flash("Clave actualizada.", "success")
            return redirect(default_redirect_for_role(session.get("role")))

        con.close()
        return render_template("password_change.html")

    @bp.route("/acceso-denegado", endpoint="access_denied")
    def access_denied():
        return render_template("access_denied.html")

    return bp
