const { Client, LocalAuth } = require("whatsapp-web.js");
const express = require("express");
const qrcode = require("qrcode-terminal");

const app = express();
app.use(express.json());

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "/app/.wwebjs_auth" }),
  puppeteer: {
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-first-run",
      "--no-zygote",
      "--single-process",
    ],
  },
});

let ready = false;

client.on("qr", (qr) => {
  console.log("\n=== SCAN THIS QR CODE WITH WHATSAPP ===");
  console.log("WhatsApp → Linked Devices → Link a Device\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("WhatsApp: authenticated ✓");
});

client.on("ready", () => {
  ready = true;
  console.log("WhatsApp: client ready — sidecar accepting requests on :3333");
});

client.on("disconnected", (reason) => {
  ready = false;
  console.warn("WhatsApp: disconnected —", reason);
});

client.initialize();

// ── Health check ─────────────────────────────────────────────────────────────
app.get("/health", (req, res) => {
  res.json({ ready });
});

// ── Phone lookup ──────────────────────────────────────────────────────────────
app.get("/lookup/:phone", async (req, res) => {
  if (!ready) {
    return res.status(503).json({ error: "WhatsApp client not ready — scan QR first" });
  }

  // Normalise: strip +, spaces, dashes
  const number = req.params.phone.replace(/[+\s\-()]/g, "");
  const jid = `${number}@c.us`;

  try {
    const registered = await client.isRegisteredUser(jid);
    if (!registered) {
      return res.json({ registered: false });
    }

    const contact = await client.getContactById(jid);
    const profile_pic = await client.getProfilePicUrl(jid).catch(() => null);
    const about = await contact.getAbout().catch(() => null);

    return res.json({
      registered: true,
      name: contact.pushname || contact.name || null,
      profile_pic,
      about,
    });
  } catch (err) {
    console.error("WhatsApp lookup error:", err);
    return res.status(500).json({ error: String(err) });
  }
});

app.listen(3333, () => {
  console.log("WA sidecar listening on :3333");
});
