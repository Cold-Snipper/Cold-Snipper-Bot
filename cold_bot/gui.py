import re
import threading
import webbrowser
from tkinter import Tk, ttk, messagebox, Toplevel, Text, END, StringVar, BooleanVar, Button, Label, Listbox

import json
import yaml

from silos.config_loader import ConfigLoader
from silos.email_sender import get_viable_leads, send_email, update_lead_status, reset_db


def fetch_viable_leads(db_path: str):
    return get_viable_leads(db_path)


class ColdBotGUI:
    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config = ConfigLoader.load_config(config_path)
        self.db_path = self.config["database"]
        self.root = Tk()
        self.root.title("Cold Bot")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.crm_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.crm_frame, text="CRM")

        self.targets_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.targets_frame, text="Targets")

        self.tree = ttk.Treeview(
            self.crm_frame,
            columns=("ID", "Title", "Price", "Location", "Contact", "URL", "Reason", "Rating", "Status"),
            show="headings",
        )
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by(c, False))
            self.tree.column(col, width=120)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.show_details)

        controls = ttk.Frame(self.crm_frame)
        controls.pack(fill="x")
        Button(controls, text="Refresh", command=self.refresh).pack(side="left")
        Button(controls, text="Contact Selected", command=self.contact_selected).pack(side="left")
        Button(
            controls,
            text="RESET DB",
            command=self.reset_db,
            bg="yellow",
            fg="black",
            font=("Arial", 14, "bold"),
        ).pack(side="right", padx=10, pady=5)

        self._build_targets_tab()
        self.refresh()

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for lead in fetch_viable_leads(self.db_path):
            self.tree.insert(
                "",
                END,
                values=(
                    lead["id"],
                    lead["title"],
                    lead["price"],
                    lead["location"],
                    lead["contact"],
                    lead.get("listing_url", ""),
                    lead["viability_reason"],
                    lead["rating"],
                    lead["status"],
                ),
            )

    def sort_by(self, col: str, descending: bool) -> None:
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children("")]
        try:
            data.sort(key=lambda t: float(t[0]) if t[0] else 0, reverse=descending)
        except ValueError:
            data.sort(key=lambda t: t[0], reverse=descending)
        for index, (_, child) in enumerate(data):
            self.tree.move(child, "", index)
        self.tree.heading(col, command=lambda: self.sort_by(col, not descending))

    def show_details(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        lead_id = item["values"][0]
        lead = next((l for l in fetch_viable_leads(self.db_path) if l["id"] == lead_id), None)
        if not lead:
            return
        popup = Toplevel(self.root)
        popup.title("Lead Details")
        text = Text(popup, width=80, height=20)
        text.pack(fill="both", expand=True)
        text.insert(
            END,
            f"Title: {lead['title']}\nPrice: {lead['price']}\nLocation: {lead['location']}\n"
            f"Contact: {lead['contact']}\nListing URL: {lead.get('listing_url','')}\n"
            f"Rating: {lead['rating']}\nReason: {lead['viability_reason']}\n"
            f"Factors: {lead['qualification_factors']}\n\nDescription:\n{lead['description']}",
        )
        text.config(state="disabled")
        if lead.get("listing_url"):
            Button(
                popup,
                text="Open Listing",
                command=lambda: webbrowser.open(lead["listing_url"]),
            ).pack()

    def contact_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("CRM", "Select at least one lead.")
            return
        lead_id = self.tree.item(selected[0])["values"][0]
        lead = next((l for l in fetch_viable_leads(self.db_path) if l["id"] == lead_id), None)
        if not lead:
            return

        dialog = Toplevel(self.root)
        dialog.title("Contact Selected")
        mode = StringVar(value="email")
        Label(dialog, text="Choose contact mode:").pack()
        ttk.Radiobutton(dialog, text="Email", variable=mode, value="email").pack(anchor="w")
        ttk.Radiobutton(dialog, text="WhatsApp", variable=mode, value="whatsapp").pack(anchor="w")

        def do_contact():
            if mode.get() == "email":
                if "@" not in lead["contact"]:
                    messagebox.showwarning("Email", "No email found for this lead.")
                    return
                subject = self.config["message_templates"]["email"]["subject"]
                body = self.config["message_templates"]["email"]["body"]
                body = body.replace("[property desc]", lead["title"])
                body = body.replace("[Owner]", "Owner")
                confirmed = messagebox.askyesno("Confirm", f"{subject}\n\n{body}")
                if not confirmed:
                    return
                threading.Thread(
                    target=self._send_email_thread,
                    args=(lead, subject, body),
                    daemon=True,
                ).start()
            else:
                phone = self._extract_phone(lead["description"])
                if not phone:
                    messagebox.showwarning("WhatsApp", "No phone found for this lead.")
                    return
                body = self.config["message_templates"]["whatsapp"]["body"]
                body = body.replace("[property]", lead["title"])
                body = body.replace("[Owner]", "Owner")
                confirmed = messagebox.askyesno("Confirm", body)
                if not confirmed:
                    return
                url = f"https://wa.me/{phone}?text={body}"
                webbrowser.open(url)
                update_lead_status(self.db_path, lead["id"], "Contacted")
            dialog.destroy()

        Button(dialog, text="Proceed", command=do_contact).pack()

    def _send_email_thread(self, lead, subject: str, body: str) -> None:
        ok = send_email(
            lead["contact"],
            body,
            self.config["email"]["from"],
            self.config["email"]["app_password"],
            self.config["email"]["smtp_host"],
            self.db_path,
            self.config["limits"]["max_contacts_per_hour"],
        )
        if ok:
            update_lead_status(self.db_path, lead["id"], "Contacted")
            messagebox.showinfo("Email", "Sent.")
        else:
            messagebox.showerror("Email", "Send failed.")

    def _extract_phone(self, text: str) -> str:
        match = re.search(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", text)
        return match.group(0) if match else ""

    def reset_db(self) -> None:
        confirmed = messagebox.askyesno(
            "Reset DB",
            "This will delete all leads and contacts. Continue?",
        )
        if not confirmed:
            return
        reset_db(self.db_path)
        self.refresh()

    def _build_targets_tab(self) -> None:
        Label(self.targets_frame, text="Country").pack(anchor="w")
        self.country_var = StringVar(value=(self.config.get("countries") or ["US"])[0])
        self.country_dropdown = ttk.Combobox(
            self.targets_frame,
            textvariable=self.country_var,
            values=self.config.get("countries") or ["US"],
        )
        self.country_dropdown.pack(anchor="w", fill="x")
        self.country_dropdown.bind("<<ComboboxSelected>>", lambda _e: self._refresh_groups())

        self.marketplace_var = BooleanVar(
            value=bool(self.config.get("facebook", {}).get("marketplace_enabled", False))
        )
        ttk.Checkbutton(
            self.targets_frame,
            text="Facebook Marketplace",
            variable=self.marketplace_var,
        ).pack(anchor="w")

        self.fb_message_var = BooleanVar(
            value=bool(self.config.get("facebook", {}).get("messaging_enabled", False))
        )
        ttk.Checkbutton(
            self.targets_frame,
            text="Facebook Messaging Enabled",
            variable=self.fb_message_var,
        ).pack(anchor="w")

        Label(self.targets_frame, text="Facebook Rental Groups").pack(anchor="w")
        self.groups_list = Listbox(self.targets_frame, height=6)
        self.groups_list.pack(fill="both", expand=True)
        self._refresh_groups()

        Button(self.targets_frame, text="Save Targets", command=self._save_targets).pack(anchor="e")

    def _refresh_groups(self) -> None:
        self.groups_list.delete(0, END)
        fb_cfg = self.config.get("facebook", {})
        groups = fb_cfg.get("groups_by_country", {}).get(self.country_var.get(), [])
        db_path = fb_cfg.get("groups_database")
        if db_path:
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    db = json.load(f)
                db_groups = db.get(self.country_var.get(), [])
                for entry in db_groups:
                    groups.append(entry.get("url", ""))
            except Exception:
                pass
        for g in groups:
            if g:
                self.groups_list.insert(END, g)

    def _save_targets(self) -> None:
        self.config.setdefault("facebook", {})
        self.config["facebook"]["marketplace_enabled"] = self.marketplace_var.get()
        self.config["facebook"]["messaging_enabled"] = self.fb_message_var.get()
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, sort_keys=False)


if __name__ == "__main__":
    ColdBotGUI().root.mainloop()
