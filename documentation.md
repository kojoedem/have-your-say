# Have Your Say — System Documentation & Developer Guide

Welcome to the comprehensive, developer-focused and architectural system documentation for **Have Your Say**, a next-generation anonymous, truth-driven, and ephemeral discussion platform.

This platform allows users to share short, temporary statements or claims ("Says"), upload images or short videos, participate in truth-validation loops, comment anonymously, and view trending discussions. Every post has a strict 12-hour lifespan and auto-expires, promoting dynamic real-time interaction.

---

## Table of Chapters

- [Chapter 1: Authentication & Secure Sign-In (Terms, SMTP & Telegram Bot OTPs)](#chapter-1-authentication--secure-sign-in-terms-smtp--telegram-bot-otps)
- [Chapter 2: User Identity, Pseudonyms & Geolocation Profiling](#chapter-2-user-identity-pseudonyms--geolocation-profiling)
- [Chapter 3: Content Creation, Says Generation & Video Trimmer Mechanics](#chapter-3-content-creation-says-generation--video-trimmer-mechanics)
- [Chapter 4: Decentralized Truth-Validation & User Credibility Engine](#chapter-4-decentralized-truth-validation--user-credibility-engine)
- [Chapter 5: Discussion Architecture, Responsive Layouts & Sticky Navigation](#chapter-5-discussion-architecture-responsive-layouts--sticky-navigation)
- [Chapter 6: Backend API Architecture, Database Schema & Deployment Guide](#chapter-6-backend-api-architecture-database-schema--deployment-guide)

---

## Chapter 1: Authentication & Secure Sign-In (Terms, SMTP & Telegram Bot OTPs)

The platform implements a highly optimized, dual-option authentication layer using email or phone number verification to keep user credentials fully separate from real-world accounts.

<p align="center">
  <img src="logo.png" width="220" alt="Have Your Say Logo">
</p>

### 1.1 The Login Interface Page & Elements
The sign-in interface is dynamically built in `templates/index.html` inside the `#auth-screen` section.
* **Layout Design:** Styled with Tailwind CSS as a centered `max-w-md` card container embedded in a dark theme (`bg-slate-950`).
* **Interactive Tabs:** Built using two tab buttons (`#tab-telegram` and `#tab-email`) which let the user switch between **Telegram Bot** and **Email Address** authentication channels. Switching tabs hides and shows respective inputs dynamically, ensuring a clean uncluttered screen.
* **Phone Input Element:** A specialized telephone element (`#phone`) equipped with validation patterns (`pattern="^\+?[0-9\s\-()]{5,25}$"`) requiring at least 5 digits to allow either deep-linked phone number delivery or native Telegram Chat IDs.
* **Email Input Element:** An email element (`#email`) with a secure placeholder instructing users to supply an email address for real SMTP OTP code dispatch.

<p align="center">
  <img src="first-image.png" width="550" alt="Login Interface Page - Step 1">
</p>

### 1.2 The Terms and Conditions (T&C) Consent Gatekeeper
Before any OTP request is allowed to fire, the system strictly enforces the acceptance of Terms and Conditions:
* **Interactive Read Button:** Clicking on the `#terms-read-btn` trigger spawns a dedicated modal (`#terms-conditions-modal`) overlaying the screen.
* **Detailed Terms Modal:** Displays structural guidelines regarding User Responsibility, Acceptable Use, Respect, and No-Guarantee clauses.
* **Hidden Acceptance Checkbox:** Accepting terms inside the modal checks a hidden `#accept-terms` validation checkbox on the client side, changes the read button text to *"Review Terms & Conditions"*, and reveals a green verified `#accepted-badge` status badge.
* **Guard Lock:** If the checkbox is unchecked, submitting the OTP request form alerts the user and refuses to issue an API request.

### 1.3 OTP Generation & Backend Dispatching Flow
When a user submits their email or phone number/ID:
1. **Endpoint Call:** The frontend sends a `POST /api/auth/otp-request` payload.
2. **Identification Strategy:** The backend parses whether a phone number/ID or an email has been submitted.
3. **Random Code Generation:** The backend generates a secure 6-digit random number (e.g. `123456`) in `otp.py`.
4. **Expiration Timeframe:** Saves the OTP in the user record with a strict 5-minute lifespan (`otp_expires`).

<p align="center">
  <img src="second-page.png" width="550" alt="OTP Verification View - Step 2">
</p>

### 1.4 Dual-Option Channel Delivery Mechanics
The OTP is delivered according to the active tab channel chosen:
* **Email OTP Verification Flow:**
  * Uses standard python `smtplib` library inside `email_sender.py`.
  * Evaluates port configurations (e.g., SSL on port `465` or TLS starttls on port `587`).
  * If successful, delivers a clean, secure email message to the user.
  * Under testing/dev environments lacking SMTP credentials, the backend falls back to a Mock mode when the `MOCK_SMTP=True` environment variable is defined.
* **Telegram Bot Verification Flow:**
  * If the user's phone/ID is already mapped to their Telegram account, the bot directly sends an asynchronous OTP message via Telegram Bot API `/sendMessage` in a `BackgroundTasks` loop.
  * If the account is new or unlinked, the backend returns a `"redirect"` status pointing to a Telegram deep link: `https://t.me/<BOT_USERNAME>?start=login_<phone>`.
  * The user is prompted to click the link, opening their Telegram App to link their ID. The background bot handler automatically maps their `telegram_chat_id`, generates an OTP, sends it directly in the chat, and changes their status to verified.
  * For local simulation, a **Mock SMS Dispatcher** banner (`#mock-otp-banner`) is displayed on the client screen with a **Copy Code** clipboard shortcut, ensuring developer convenience. **Important:** To preserve email privacy, this mock banner is automatically hidden when using the Email authentication option.

### 1.5 Code Verification & Secure Session Handshake
1. **Verification Form Transition:** The client side immediately transitions to the OTP verification form (`#otp-verify-form`) showing an descriptive notice of where the code was sent.
2. **Endpoint Submission:** The user enters their 6-digit code, firing a `POST /api/auth/otp-verify`.
3. **Session Handshake:**
   * If code matches and hasn't expired, a new cryptographically secure 32-character session token is stored on the user table (`session_token`).
   * The backend returns a response setting the cookie `session_token` with `HttpOnly`, `SameSite=Lax`, and `Max-Age=30 days`.
   * **Single-Session Enforcement:** Overwriting the `session_token` column upon a new OTP login automatically invalidates any other active session cookies across different devices.

---

## Chapter 2: User Identity, Pseudonyms & Geolocation Profiling

*Have Your Say* relies on a strict identity decoupling pattern where users can set their internal beliefs and custom aliases, while being fully masked by periodic pseudonym rotations and geolocated connections.

### 2.1 Periodic Pseudonym Rotation Logic
To prevent long-term mapping of anonymous users, the platform implements an automated pseudonym assignment algorithm:
* **Creation Strategy:** Each username is derived from a pairing of random Adjectives (`Silent`, `Quiet`, `Hidden`, `Shadow`, `Deep`, `Bold`, etc.) and Nouns (`Thinker`, `Voice`, `Echo`, `Philosopher`, `Dreamer`, etc.), with a unique 4-character hex suffix added to guarantee database unique constraints (e.g., `@Quiet_Echo_7f1a`).
* **12-Hour Decay Loop:** The backend tracks the last pseudonym update time using `pseudonym_updated_at`. Upon any request to authenticated user context, the system inspects this timestamp. If more than 12 hours have elapsed, or on any fresh login, a new random username/alias is assigned and saved in SQLite.

### 2.2 Geolocation Mapping & Connection Profiling
When first launching the profile setup modal:
* **API Integration:** The client-side JS calls an asynchronous IP-based country lookup (`https://ipapi.co/json/`).
* **Graceful Fallbacks:** If the client is behind an adblocker or is offline, the script falls back to parsing the local timezone format (e.g. `Europe/Paris` converted to `Paris Region`), or ultimately defaults to `"Earth Orbit"` to maintain visual elegance.
* **Live UI Status:** Displays the detected location dynamically inside the Profile Settings card.

### 2.3 User Profile Setup Modal (#profile-screen)
* **Custom Profile View:** If an authenticated user does not have a username/alias yet, they are presented with the Profile Settings layout.
* **Fields Structure:** Includes inputs for their customized Pseudonym/Alias and an optional *"What I Believe In"* text area where they can write their guiding philosophies.
* **Boolean Safety Guard:** When the profile update handler is called from various screens, it explicitly passes boolean parameters (e.g., `handleUpdateProfile(false, event)`) to prevent the browser's native `event` object from implicitly overriding boolean arguments, which would trigger 422 validation errors.

---

## Chapter 3: Content Creation, Says Generation & Video Trimmer Mechanics

Users share statements, claims, and media through the *"Create a Say"* system. It includes advanced browser-side compression, segment selection, and owner permissions.

### 3.1 Content Types Supported
The creation form accepts three formats of content:
1. **Text Posts:** Standard written statements, opinions, or claims.
2. **Image Attachments:** Form-uploaded JPG, PNG, or WEBP photos.
3. **Short-form Video Clips:** Standard video formats with a strict 60-second limit.

### 3.2 WhatsApp-Style Video Cutter & Frame Selector
When a user selects a video file, a highly interactive, custom trimming interface (`#video-cutter-frame`) is launched overlaying the creation screen:

<p align="center">
  <img src="second-image.png" width="550" alt="Media Attachment & Trimmer Layout">
</p>

* **Scrubber Controls:** Users can play/pause the video, adjust a range range slider (`#video-scrubber`), and view the current playback time.
* **Dynamic Timeline Strip:** The system automatically extracts 5 thumbnail frames from the video file locally and renders them as a timeline strip to make navigation incredibly easy.
* **Start and End Trim Offsets:** Users can configure precisely when the trimmed clip should start and end, with validation limiting the chosen segment to a maximum of 60 seconds.
* **Actions:**
  * **Convert Current Frame:** Grabs the frame currently on screen and converts it to a lightweight GIF.
  * **Cut & Convert:** Takes the trimmed segment and compiles it into an animated GIF.

### 3.3 Dynamic Video-to-GIF Conversion (Browser-Side Processing)
To maximize privacy and optimize server storage, the client-side JavaScript converts video selections into highly compressed animated GIFs using `gifshot.js`:
* **Conversion Parameters:** Built with optimized frame rates (15 frames max) and resolution parameters (`320x240`) to ensure instant generation.
* **Overlay Loader:** While compiling, an overlay `#video-to-gif-overlay` prevents double-submission and displays a beautiful progress spinner.
* **Sync Form Append:** Once completed, the raw base64 data is converted to an uploadable `File` and attached to the FormData payload.

### 3.4 Backend Video Streaming and Validation
If a raw video upload bypasses GIF conversion and is sent directly:
* **Size Enforcement:** The backend dynamically checks the file size. If the video file is larger than **50MB**, the file is unlinked and rejected with a `400 Bad Request` error.
* **Duration Constraints:** The backend runs `ffprobe` to determine the video duration. If it exceeds 60 seconds, it is rejected.
* **Video Playback Stream:** Accepted videos are kept intact inside `videos/original` and streamed natively via `/api/videos/{video_id}/play`. The client UI displays them inside standard `<video controls>` elements. To guarantee reliable timeline thumbnail generation across all browsers, the client-side script calls `.load()` explicitly on HTML5 elements whenever their `.src` attribute is dynamically modified.

### 3.5 Content Lifespan (12-Hour Decay Loop)
Every Topic and Comment contains an `expires_at` column mapped to exactly **12 hours** past its creation time. The backend filters all fetch queries to retrieve only active topics where `expires_at > current_time`. Once expired, the content organically disappears from active feeds.

### 3.6 Download Permission Control (Creator Control)
Topic creators can control whether their conversation can be exported by the community:
* **Allow Download:** If checked (`allow_download = True`), anyone can download the anonymized discussion.
* **Disable Download:** If disabled, the export controls are locked.
* **Owner Switch:** Topic creators can dynamically toggle this permission at any time.

---

## Chapter 4: Decentralized Truth-Validation & User Credibility Engine

Instead of arbitrary likes, *Have Your Say* implements a decentralized truth-validation mechanism where statements are actively verified or disverified by the community.

### 4.1 Cast a Validation Vote
Authenticated users can vote on topics through `POST /api/topics/{topic_id}/vote` with a `vote_type` of either `"verify"` or `"disverify"`.
* **Retraction Logic:** Clicking the same vote twice retracts the vote, while clicking the opposite option updates their active choice dynamically.

### 4.2 Dynamic User Credibility Calculation (Laplace Smoothing)
Voters' influence is weighted by their credibility score, calculated dynamically using a smoothed Laplace formula on the backend:

$$\text{Score} = 50.0 + 50.0 \times \left( \frac{N_{\text{verified}} - N_{\text{disverified}}}{N_{\text{verified}} + N_{\text{disverified}} + 2} \right) + \text{Participation Bonus}$$

* **Laplace Smoothing:** Adding $2$ in the denominator dampens extreme swings for users with very few posts.
* **Participation Bonus:** Adds $+1$ per comment made on other users' topics (capped at a maximum bonus of $+10$).
* **Score Cap:** The final score is rounded and capped strictly between $10\%$ and $100\%$.
* **Recursion-Safe Protection:** To prevent infinite database queries during nested lookups, a recursion limit is enforced.

### 4.3 dynamic Topic Classification Statuses
Using the credibility scores, a claim is dynamically classified as:
* **Verified (Trusted):** If the weighted verify votes exceed weighted disverify votes by at least $1.5$.
* **Disverified (Rejected):** If the weighted disverify votes exceed weighted verify votes by at least $1.5$.
* **Disputed (Uncertain):** If the difference is less than $1.5$.

---

## Chapter 5: Discussion Architecture, Responsive Layouts & Sticky Navigation

The frontend is a single-page layout optimized for mobile and desktop screens, featuring real-time discussion hierarchies and sticky layouts.

<p align="center">
  <img src="fourth-image.png" width="550" alt="Main Feed & Responsive Column Layout">
</p>

### 5.1 Responsive Layout Grid
The layout adjusts gracefully across screen sizes:
* **Desktop Layout:** Organizes the feed in a 12-column grid (`grid-cols-12`):
  * **Main Column (8 columns):** Contains the *"Create a Say"* card, Hot Takes Spot, and the Main Feed of active conversations.
  * **Sidebar Column (4 columns):** Displays Identity/Belief Settings, and the Trending Discussions list.
* **Mobile Layout (< 1024px):** Adapts to a clean, focused single-column layout:
  * **Mobile Top Header:** Replaces desktop navigation, featuring a circular profile avatar, dynamic breadcrumb pill containing their Identity/Belief, and a quick logout action.
  * **Mobile Bottom Sticky Bar:** Provides navigation triggers to switch active sections between **Home** and **Trending**.
  * **Floating Action Button (FAB):** Pins a glowing gradient button (`#mobile-fab`) to the bottom-left of the viewport. Clicking it opens the *"Create a Say"* modal overlay.

### 5.2 Trending Discussions Sidebar Card
The `#trending-container` displays high-engagement topics:
* **Max Height Restriction:** Formatted with a CSS rule of `max-h-64` and `overflow-y-auto` to allow comfortable scrolling.
* **Text Hover Preview:** Items utilize native HTML `title` attributes so users can hover to read the full claim.
* **Mobile Interactivity:** Clicking any trending item on mobile viewports automatically switches the bottom navigation tab to the `home` feed and smoothly scrolls the target conversation card into view with a highlight animation.

### 5.3 Hierarchical Nested Comments & Pins
Comments support a threaded, self-referential parent-child structure:
* **WhatsApp-Style Alternating Bubbles:** Comments are rendered in alternating left-aligned (gray) and right-aligned (greenish-emerald) bubbles to read like a modern chat thread.
* **Comment Pinned Algorithm:** To highlight high-retention discussions, the system programmatically pins the top-level comment containing the highest count of nested replies, rendering it at the very top of the comments container.
* **Collapsible Indicator:** Comments are collapsed and hidden by default, expandable via the comments indicator count button.

---

## Chapter 6: Backend API Architecture, Database Schema & Deployment Guide

This chapter outlines the SQLite schema models, critical FastAPI endpoints, and security mechanisms.

### 6.1 Database Models and Relationships (`database.py`)
```
                                +-----------------------+
                                |         User          |
                                +-----------------------+
                                | - id (PK)             |
                                | - phone/email (Unique)|
                                | - telegram_chat_id    |
                                | - alias/username      |
                                | - session_token       |
                                +-----------------------+
                                   |      |         |
         +-------------------------+      |         +-----------------------+
         |                                |                                 |
         v                                v                                 v
+------------------+             +------------------+             +------------------+
|      Topic       |             |     Comment      |             |      Video       |
+------------------+             +------------------+             +------------------+
| - id (PK)        |             | - id (PK)        |             | - id (PK)        |
| - user_id (FK)   |             | - topic_id (FK)  |             | - user_id (FK)   |
| - text           |             | - user_id (FK)   |             | - topic_id (FK)  |
| - image_url      |-----------> | - parent_id (FK) |             | - filename       |
| - allow_download |             | - text           |             | - duration       |
| - expires_at     |             +------------------+             +------------------+
+------------------+
```

### 6.2 Primary REST Endpoints (`main.py`)
* **`POST /api/auth/otp-request`** — Validates the input, generates a 6-digit verification code, and dispatches it via SMTP Email or Telegram Bot.
* **`POST /api/auth/otp-verify`** — Validates the received code and creates an HTTP session cookie.
* **`POST /api/auth/profile`** — Updates the user's alias and belief.
* **`GET /api/auth/me`** — Validates the user's active session and calculates their credibility score.
* **`POST /api/topics`** — Publishes a new Say.
* **`GET /api/topics`** — Fetches active, unexpired conversations.
* **`POST /api/topics/{topic_id}/vote`** — Casts or retrains truth validation votes.
* **`POST /api/topics/{topic_id}/comments`** — Creates comments or nested replies.
* **`GET /api/videos/{video_id}/play`** — Streams video original files.

### 6.3 Security Mechanisms
* **Cross-Site Scripting (XSS) Prevention:**
  The frontend uses an `escapeHTML` helper function to sanitize all dynamic user inputs (such as usernames, texts, comments, and beliefs) before injection into the DOM:
  ```javascript
  function escapeHTML(str) {
      if (!str) return '';
      return str
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
  }
  ```
* **Ownership Controls:**
  Topics and comments are restricted so that edit (`PUT`) and delete (`DELETE`) API actions are only allowed for the authenticated user who created them.

### 6.4 Developer Deployment Commands
To spin up the platform in local or staging environments:
1. **Ensure environment stub exists (`env_var.py`):**
   ```bash
   cat <<EOF > env_var.py
   BOT_TOKEN = "your_bot_token"
   BOT_USERNAME = "your_bot_username"
   SMTP_SERVER = "smtp.gmail.com"
   SMTP_PORT = 587
   SMTP_USERNAME = "your_email@gmail.com"
   SMTP_PASSWORD = "your_app_password"
   SMTP_SENDER = "your_email@gmail.com"
   EOF
   ```
2. **Start the Uvicorn development server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
3. **Execute unit and integration tests:**
   ```bash
   pytest
   ```
