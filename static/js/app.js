        // --- XSS Prevention Escape Helper ---
        function escapeHTML(str) {
            if (!str) return '';
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        // --- Global States ---
        let currentUser = null;
        let detectedLocation = "Anonymous Location";
        let countdownIntervals = [];

        // Run on Page Load
        window.addEventListener('DOMContentLoaded', async () => {
            lucide.createIcons();
            await fetchUserLocation();
            await checkAuth();
            startBackgroundPolling();
        });

        // --- GEOLOCATION ENGINE ---
        async function fetchUserLocation() {
            try {
                // Fetch from a robust free geolocation service
                const res = await fetch('https://ipapi.co/json/');
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.city && data.country_name) {
                        detectedLocation = `${data.city}, ${data.country_name}`;
                    } else if (data && data.country_name) {
                        detectedLocation = data.country_name;
                    }
                }
            } catch (err) {
                console.log("IP lookup failed, using offline fallback...", err);
                try {
                    // Try to generate timezone city
                    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                    if (tz && tz.includes('/')) {
                        const parts = tz.split('/');
                        const region = parts[0];
                        const city = parts[1].replace('_', ' ');
                        detectedLocation = `${city} Region`;
                    }
                } catch (fallbackErr) {
                    detectedLocation = "Earth Orbit";
                }
            }
            const locationDisplay = document.getElementById('user-location-display');
            if (locationDisplay) {
                locationDisplay.innerText = `Location: ${detectedLocation}`;
            }
        }

        // --- AUTH SERVICES ---
        let activeAuthTab = 'telegram';

        function switchAuthTab(tab) {
            activeAuthTab = tab;
            const tabTelegram = document.getElementById('tab-telegram');
            const tabEmail = document.getElementById('tab-email');
            const phoneContainer = document.getElementById('phone-input-container');
            const emailContainer = document.getElementById('email-input-container');
            const phoneInput = document.getElementById('phone');
            const emailInput = document.getElementById('email');
            const requestBtn = document.getElementById('request-otp-btn');

            if (tab === 'telegram') {
                tabTelegram.classList.add('border-indigo-500', 'text-indigo-400');
                tabTelegram.classList.remove('border-transparent', 'text-slate-400');
                tabEmail.classList.add('border-transparent', 'text-slate-400');
                tabEmail.classList.remove('border-indigo-500', 'text-indigo-400');

                phoneContainer.classList.remove('hidden');
                emailContainer.classList.add('hidden');
                phoneInput.required = true;
                emailInput.required = false;

                requestBtn.innerHTML = `<span>Verify via Telegram</span><i data-lucide="send" class="h-5 w-5"></i>`;
            } else {
                tabEmail.classList.add('border-indigo-500', 'text-indigo-400');
                tabEmail.classList.remove('border-transparent', 'text-slate-400');
                tabTelegram.classList.add('border-transparent', 'text-slate-400');
                tabTelegram.classList.remove('border-indigo-500', 'text-indigo-400');

                emailContainer.classList.remove('hidden');
                phoneContainer.classList.add('hidden');
                emailInput.required = true;
                phoneInput.required = false;

                requestBtn.innerHTML = `<span>Verify via Email</span><i data-lucide="send" class="h-5 w-5"></i>`;
            }
            lucide.createIcons();
        }

        async function checkAuth() {
            try {
                const res = await fetch('/api/auth/me');
                const data = await res.json();

                if (data.authenticated) {
                    currentUser = data.user;
                    if (currentUser.has_profile) {
                        showAppScreen();
                    } else {
                        showProfileScreen();
                    }
                } else {
                    showAuthScreen();
                }
            } catch (err) {
                console.error("Auth check failed:", err);
                showAuthScreen();
            }
        }

        function showAuthScreen() {
            document.getElementById('auth-screen').classList.remove('hidden');
            document.getElementById('profile-screen').classList.add('hidden');
            document.getElementById('app-screen').classList.add('hidden');
            document.getElementById('header-user-controls').classList.add('hidden');
            showRequestOTPForm();
        }

        function showRequestOTPForm() {
            document.getElementById('otp-request-form').classList.remove('hidden');
            document.getElementById('otp-verify-form').classList.add('hidden');
            document.getElementById('mock-otp-banner').classList.add('hidden');
            const telegramBtn = document.getElementById('telegram-link-btn');
            if (telegramBtn) telegramBtn.remove();
        }

        function showVerifyOTPForm(identifier, otpCode, telegramLink = null) {
            document.getElementById('otp-request-form').classList.add('hidden');
            document.getElementById('otp-verify-form').classList.remove('hidden');

            // Pop the banner showing the Mock OTP ONLY for Telegram (since email mocking is completely removed as requested)
            const mockBanner = document.getElementById('mock-otp-banner');
            if (activeAuthTab === 'telegram') {
                document.getElementById('mock-otp-value').innerText = otpCode;
                mockBanner.classList.remove('hidden');

                const bannerTitle = mockBanner.querySelector('h3');
                const bannerText = mockBanner.querySelector('p');
                bannerTitle.innerText = "Mock Telegram/SMS Dispatcher";
                bannerText.innerHTML = `We generated code <span class="font-mono font-bold bg-amber-400 text-slate-950 px-2 py-0.5 rounded text-sm" id="mock-otp-value">${otpCode}</span> for your phone number.`;
            } else {
                mockBanner.classList.add('hidden');
            }

            const changeText = document.getElementById('change-identifier-text');
            if (changeText) {
                changeText.innerText = activeAuthTab === 'telegram' ? "Change phone number" : "Change email address";
            }

            // Display Telegram deep link button if redirecting
            const telegramBtnId = 'telegram-link-btn';
            let telegramBtn = document.getElementById(telegramBtnId);
            if (telegramLink) {
                if (!telegramBtn) {
                    telegramBtn = document.createElement('div');
                    telegramBtn.id = telegramBtnId;
                    telegramBtn.className = "mt-4 text-center";
                    telegramBtn.innerHTML = `
                        <a href="${telegramLink}" target="_blank" class="inline-flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-semibold transition-all shadow-md">
                            <i data-lucide="send" class="h-4 w-4"></i>
                            <span>Open Telegram Bot to Link Account</span>
                        </a>
                    `;
                    document.getElementById('otp-verify-form').insertBefore(telegramBtn, document.getElementById('otp-verify-form').firstChild);
                } else {
                    telegramBtn.querySelector('a').href = telegramLink;
                    telegramBtn.classList.remove('hidden');
                }
            } else {
                if (telegramBtn) {
                    telegramBtn.classList.add('hidden');
                }
            }

            // Focus verify input
            document.getElementById('code').value = '';
            document.getElementById('code').focus();
            lucide.createIcons();
        }

        function copyMockOTP() {
            const code = document.getElementById('mock-otp-value').innerText;
            navigator.clipboard.writeText(code);
            alert("Code copied to clipboard: " + code);
        }

        async function handleRequestOTP(e) {
            e.preventDefault();
            const phoneInput = document.getElementById('phone');
            const emailInput = document.getElementById('email');
            const fd = new FormData();

            if (activeAuthTab === 'telegram') {
                const phone = phoneInput.value.trim();
                const digits = phone.replace(/\D/g, '');
                if (digits.length < 5) {
                    alert("Please enter a valid Phone Number or Telegram Chat ID containing at least 5 digits.");
                    phoneInput.focus();
                    return;
                }
                fd.append('phone', phone);
            } else {
                const email = emailInput.value.trim();
                if (!email) {
                    alert("Please enter a valid email address.");
                    emailInput.focus();
                    return;
                }
                fd.append('email', email);
            }

            const btn = document.getElementById('request-otp-btn');
            btn.disabled = true;
            btn.innerHTML = `<span class="animate-pulse">Requesting...</span>`;

            try {
                const res = await fetch('/api/auth/otp-request', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    if (data.status === 'redirect') {
                        alert("Account not linked to Telegram yet. Redirecting to Telegram Bot...");
                        window.open(data.telegram_link, '_blank');
                        showVerifyOTPForm(data.phone || '', data.otp_code || '', data.telegram_link);
                    } else {
                        const identifier = activeAuthTab === 'telegram' ? data.phone : data.email;
                        showVerifyOTPForm(identifier, data.otp_code || '');
                    }
                } else {
                    alert(data.detail || "Error requesting OTP code.");
                }
            } catch (err) {
                console.error("OTP Request Error:", err);
                alert("Failed to reach server. Try again.");
            } finally {
                btn.disabled = false;
                if (activeAuthTab === 'telegram') {
                    btn.innerHTML = `<span>Verify via Telegram</span><i data-lucide="send" class="h-5 w-5"></i>`;
                } else {
                    btn.innerHTML = `<span>Verify via Email</span><i data-lucide="send" class="h-5 w-5"></i>`;
                }
                lucide.createIcons();
            }
        }

        async function handleVerifyOTP(e) {
            e.preventDefault();
            const phoneInput = document.getElementById('phone');
            const emailInput = document.getElementById('email');
            const code = document.getElementById('code').value.trim();
            const btn = document.getElementById('verify-otp-btn');

            btn.disabled = true;
            btn.innerHTML = `<span class="animate-pulse">Verifying...</span>`;

            try {
                const fd = new FormData();
                if (activeAuthTab === 'telegram') {
                    fd.append('phone', phoneInput.value.trim());
                } else {
                    fd.append('email', emailInput.value.trim());
                }
                fd.append('code', code);

                const res = await fetch('/api/auth/otp-verify', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    currentUser = data.user;
                    document.getElementById('mock-otp-banner').classList.add('hidden');
                    const telegramBtn = document.getElementById('telegram-link-btn');
                    if (telegramBtn) telegramBtn.remove();

                    if (currentUser.has_profile) {
                        showAppScreen();
                    } else {
                        showProfileScreen();
                    }
                } else {
                    alert(data.detail || "Invalid code. Please try again.");
                }
            } catch (err) {
                console.error("OTP Verify Error:", err);
                alert("Authentication failed.");
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>Verify and Continue</span><i data-lucide="check" class="h-5 w-5"></i>`;
                lucide.createIcons();
            }
        }

        function showProfileScreen() {
            document.getElementById('auth-screen').classList.add('hidden');
            document.getElementById('profile-screen').classList.remove('hidden');
            document.getElementById('app-screen').classList.add('hidden');
            document.getElementById('header-user-controls').classList.add('hidden');

            document.getElementById('username').value = currentUser.username || '';
            document.getElementById('belief').value = currentUser.belief || '';

            // Automatically set detected country display
            const countryEl = document.getElementById('detected-country-display');
            if (countryEl) {
                countryEl.innerText = detectedLocation || "Earth Orbit";
            }
        }

        async function handleUpdateProfile(sidebar = false, e) {
            if (e) e.preventDefault();

            let userVal, beliefVal;
            if (sidebar) {
                userVal = document.getElementById('sidebar-username').value.trim();
                beliefVal = document.getElementById('sidebar-belief').value.trim();
            } else {
                userVal = document.getElementById('username').value.trim();
                beliefVal = document.getElementById('belief').value.trim();
            }

            try {
                const fd = new FormData();
                fd.append('username', userVal);
                fd.append('belief', beliefVal);

                const res = await fetch('/api/auth/profile', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    currentUser = data.user;
                    alert("Identity details updated successfully!");
                    showAppScreen();
                } else {
                    alert(data.detail || "Failed to update profile.");
                }
            } catch (err) {
                console.error("Profile update error:", err);
                alert("Error connecting to server.");
            }
        }

        function showAppScreen() {
            document.getElementById('auth-screen').classList.add('hidden');
            document.getElementById('profile-screen').classList.add('hidden');
            document.getElementById('app-screen').classList.remove('hidden');

            // Header configuration
            document.getElementById('header-user-controls').classList.remove('hidden');
            document.getElementById('header-username').innerText = `@${currentUser.username} (You: ${currentUser.alias || ''})`;
            document.getElementById('header-username').title = `Belief: ${currentUser.belief || 'None'}`;

            const initial = currentUser.username ? currentUser.username[0].toUpperCase() : 'U';
            document.getElementById('user-avatar-initial').innerText = initial;

            // Update sidebar settings form fields
            document.getElementById('sidebar-username').value = currentUser.username;
            document.getElementById('sidebar-belief').value = currentUser.belief;

            fetchFeed();
            fetchTrending();
        }

        async function logout() {
            if (!confirm("Are you sure you want to log out?")) return;
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
                currentUser = null;
                showAuthScreen();
            } catch (err) {
                console.error("Logout failed:", err);
            }
        }


        // --- FEED & TOPIC ENGAGEMENT ---

        // Loader display for GIF conversion
        function showGifProcessingFrame(show) {
            const overlay = document.getElementById('video-to-gif-overlay');
            if (overlay) {
                if (show) {
                    overlay.classList.remove('hidden');
                } else {
                    overlay.classList.add('hidden');
                }
            }
        }

        // Globals for video trimming (WhatsApp Style)
        let currentVideoFile = null;
        let currentVideoDuration = 0;

        // Handles both images and videos
        function handleMediaSelect(event) {
            const file = event.target.files[0];
            if (!file) return;

            const previewContainer = document.getElementById('image-preview-container');
            const previewImg = document.getElementById('image-preview');
            const clearBtn = document.getElementById('remove-preview-btn');

            // If it is a video, show the WhatsApp trimmer cutter frame!
            if (file.type.startsWith('video/')) {
                currentVideoFile = file;
                const cutterFrame = document.getElementById('video-cutter-frame');
                const videoPreview = document.getElementById('cutter-preview-video');

                // Show cutter frame
                cutterFrame.classList.remove('hidden');

                // Load video preview
                const videoURL = URL.createObjectURL(file);
                videoPreview.src = videoURL;
                videoPreview.load(); // Explicit load to ensure it works reliably across all browsers!

                videoPreview.onloadedmetadata = () => {
                    currentVideoDuration = videoPreview.duration;

                    // Set default inputs
                    document.getElementById('trim-start').value = 0;
                    document.getElementById('trim-start').max = currentVideoDuration;

                    document.getElementById('trim-end').value = Math.min(60, currentVideoDuration).toFixed(1);
                    document.getElementById('trim-end').max = currentVideoDuration;

                    // Set up custom scrubber limits
                    const scrubber = document.getElementById('video-scrubber');
                    if (scrubber) {
                        scrubber.max = currentVideoDuration;
                        scrubber.value = 0;
                    }
                    const timeDisplay = document.getElementById('video-time-display');
                    if (timeDisplay) {
                        timeDisplay.innerText = `0.0s / ${currentVideoDuration.toFixed(1)}s`;
                    }
                    updatePlayPauseButtonState(false); // starts playing by default

                    // Track video time updates to synchronize the scrubber and time display
                    videoPreview.ontimeupdate = () => {
                        const scr = document.getElementById('video-scrubber');
                        if (scr) {
                            scr.value = videoPreview.currentTime;
                        }
                        const td = document.getElementById('video-time-display');
                        if (td) {
                            td.innerText = `${videoPreview.currentTime.toFixed(1)}s / ${currentVideoDuration.toFixed(1)}s`;
                        }
                    };

                    onTrimSliderChange();
                    lucide.createIcons();
                };

                // Generate the timeline strip
                generateTimelineThumbnails(file);

            } else if (file.type.startsWith('image/')) {
                // Standard image preview
                window.convertedGifFile = null;
                const reader = new FileReader();
                reader.onload = function(e) {
                    previewImg.src = e.target.result;
                    previewContainer.classList.remove('hidden');
                    clearBtn.classList.remove('hidden');
                }
                reader.readAsDataURL(file);
            }
        }

        function dataURLtoFile(dataurl, filename) {
            try {
                const arr = dataurl.split(',');
                const mime = arr[0].match(/:(.*?);/)[1];
                const bstr = atob(arr[1]);
                let n = bstr.length;
                const u8arr = new Uint8Array(n);
                while (n--) {
                    u8arr[n] = bstr.charCodeAt(n);
                }
                return new File([u8arr], filename, { type: mime });
            } catch (err) {
                console.error("Failed to convert dataURL to file:", err);
                return null;
            }
        }

        function togglePlayPause() {
            const videoPreview = document.getElementById('cutter-preview-video');
            if (videoPreview) {
                if (videoPreview.paused) {
                    videoPreview.play();
                    updatePlayPauseButtonState(false);
                } else {
                    videoPreview.pause();
                    updatePlayPauseButtonState(true);
                }
            }
        }

        function updatePlayPauseButtonState(isPaused) {
            const btn = document.getElementById('video-play-pause-btn');
            if (btn) {
                btn.innerHTML = isPaused
                    ? `<i data-lucide="play" class="h-4 w-4" id="play-pause-icon"></i>`
                    : `<i data-lucide="pause" class="h-4 w-4" id="play-pause-icon"></i>`;
                lucide.createIcons();
            }
        }

        function onVideoScrub(val) {
            const videoPreview = document.getElementById('cutter-preview-video');
            if (videoPreview) {
                videoPreview.pause();
                updatePlayPauseButtonState(true);
                videoPreview.currentTime = parseFloat(val);
            }
        }

        async function generateTimelineThumbnails(file) {
            const container = document.getElementById('timeline-thumbnails-container');
            container.innerHTML = '<div class="text-[10px] text-slate-400 py-3 text-center w-full animate-pulse">Generating WhatsApp timeline...</div>';

            try {
                const tempVideo = document.createElement('video');
                tempVideo.src = URL.createObjectURL(file);
                tempVideo.muted = true;
                tempVideo.playsInline = true;

                await new Promise(resolve => {
                    tempVideo.onloadedmetadata = () => resolve();
                });

                const duration = tempVideo.duration;
                const numThumbnails = 5;
                const timestamps = [];
                for (let i = 0; i < numThumbnails; i++) {
                    timestamps.push((duration / (numThumbnails - 1)) * i);
                }

                container.innerHTML = ''; // clear loading

                for (let t of timestamps) {
                    tempVideo.currentTime = t;
                    await new Promise(resolve => {
                        tempVideo.onseeked = () => resolve();
                    });

                    const canvas = document.createElement('canvas');
                    canvas.width = 120;
                    canvas.height = 90;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(tempVideo, 0, 0, canvas.width, canvas.height);

                    const img = document.createElement('img');
                    img.src = canvas.toDataURL('image/jpeg', 0.6);
                    img.className = "w-1/5 h-10 object-cover border border-slate-800 rounded shadow-md cursor-pointer hover:border-indigo-500 transition duration-150";
                    img.title = "Seek to " + t.toFixed(1) + "s";
                    img.onclick = () => {
                        const videoPreview = document.getElementById('cutter-preview-video');
                        if (videoPreview) {
                            videoPreview.pause();
                            updatePlayPauseButtonState(true);
                            videoPreview.currentTime = t;
                        }
                    };
                    container.appendChild(img);
                }

                URL.revokeObjectURL(tempVideo.src);
            } catch (err) {
                console.error("Timeline strip extraction failed:", err);
                container.innerHTML = '<div class="text-[10px] text-red-400 py-2 text-center w-full animate-fade-in">Timeline strip preview</div>';
            }
        }

        function onTrimSliderChange() {
            let start = parseFloat(document.getElementById('trim-start').value) || 0;
            let end = parseFloat(document.getElementById('trim-end').value) || 0;

            // Constrain start and end times
            if (start < 0) start = 0;
            if (start > currentVideoDuration) start = currentVideoDuration;
            if (end < start) end = start;
            if (end > currentVideoDuration) end = currentVideoDuration;

            // Enforce max duration of 1 minute (60 seconds)
            const maxDuration = 60;
            if (end - start > maxDuration) {
                end = start + maxDuration;
                document.getElementById('trim-end').value = end.toFixed(1);
            }

            const duration = end - start;
            document.getElementById('trim-duration-label').innerText = `${duration.toFixed(1)}s`;

            // Sync preview video currentTime to the start offset
            const videoPreview = document.getElementById('cutter-preview-video');
            if (videoPreview) {
                videoPreview.currentTime = start;
                const scrubber = document.getElementById('video-scrubber');
                if (scrubber) {
                    scrubber.value = start;
                }
            }
        }

        function cancelVideoTrim() {
            // Hide cutter frame and clear input
            document.getElementById('video-cutter-frame').classList.add('hidden');
            const videoPreview = document.getElementById('cutter-preview-video');
            if (videoPreview) {
                videoPreview.src = "";
            }
            clearImagePreview();
        }

        function extractVideoFrame() {
            const videoPreview = document.getElementById('cutter-preview-video');
            if (!videoPreview || !currentVideoFile) return;

            // Hide Cutter Frame and Show processing screen overlay
            document.getElementById('video-cutter-frame').classList.add('hidden');
            showGifProcessingFrame(true);

            let start = videoPreview.currentTime || 0;
            let totalDuration = videoPreview.duration || 10;
            let clipDuration = 1.5; // Short, lightweight clip to capture a "feel" of the video as an animated GIF
            if (start + clipDuration > totalDuration) {
                start = Math.max(0, totalDuration - clipDuration);
            }

            const blobURL = URL.createObjectURL(currentVideoFile);

            // Create highly optimized animated GIF for lightning fast conversion and tiny upload size
            gifshot.createGIF({
                video: [blobURL],
                offset: start,
                videoDuration: clipDuration,
                numFrames: 10, // Fewer frames for extremely rapid processing
                interval: clipDuration / 10,
                gifWidth: 320, // Reduced resolution for quick upload and rendering
                gifHeight: 240,
                sampleInterval: 10, // Optimized pixel sampling factor for speedy color palette building
                numWorkers: 2, // Stable multi-threaded frame processing
                keepCameraOn: false
            }, function (obj) {
                showGifProcessingFrame(false);
                URL.revokeObjectURL(blobURL);

                if (obj.error) {
                    alert("Error converting frame to GIF: " + obj.errorMsg);
                    return;
                }

                const previewContainer = document.getElementById('image-preview-container');
                const previewImg = document.getElementById('image-preview');
                const clearBtn = document.getElementById('remove-preview-btn');

                const base64Data = obj.image;
                previewImg.src = base64Data;
                previewContainer.classList.remove('hidden');
                clearBtn.classList.remove('hidden');

                // Synchronously and instantly convert the base64 data to File to eliminate any race conditions!
                window.convertedGifFile = dataURLtoFile(base64Data, "extracted-frame.gif");
            });
        }

        function confirmVideoTrim() {
            if (!currentVideoFile) return;

            let start = parseFloat(document.getElementById('trim-start').value) || 0;
            let end = parseFloat(document.getElementById('trim-end').value) || 0;
            let duration = end - start;

            if (duration <= 0) {
                alert("Please select a valid clip duration.");
                return;
            }

            // Hide Cutter Frame and Show processing screen overlay
            document.getElementById('video-cutter-frame').classList.add('hidden');
            showGifProcessingFrame(true);

            const blobURL = URL.createObjectURL(currentVideoFile);

            // Ultra-optimized parameters for lightning fast GIF conversion and tiny upload size
            gifshot.createGIF({
                video: [blobURL],
                offset: start,
                videoDuration: duration,
                numFrames: 15, // 15 frames is extremely lightweight and fast
                interval: duration / 15,
                gifWidth: 320, // Reduced resolution for fast upload and speedy conversion
                gifHeight: 240,
                sampleInterval: 10, // Optimized pixel sampling factor for rapid color palette building
                numWorkers: 2, // Stable multi-threaded frame processing
                keepCameraOn: false
            }, function (obj) {
                showGifProcessingFrame(false);
                URL.revokeObjectURL(blobURL);

                if (obj.error) {
                    alert("Error converting video to GIF: " + obj.errorMsg);
                    return;
                }

                const previewContainer = document.getElementById('image-preview-container');
                const previewImg = document.getElementById('image-preview');
                const clearBtn = document.getElementById('remove-preview-btn');

                const base64Data = obj.image;
                previewImg.src = base64Data;
                previewContainer.classList.remove('hidden');
                clearBtn.classList.remove('hidden');

                // Synchronously and instantly convert the base64 data to File to eliminate any race conditions!
                window.convertedGifFile = dataURLtoFile(base64Data, "converted.gif");
            });
        }

        function clearImagePreview() {
            const input = document.getElementById('topic-image');
            input.value = "";
            window.convertedGifFile = null;
            document.getElementById('image-preview-container').classList.add('hidden');
            document.getElementById('remove-preview-btn').classList.add('hidden');
        }

        async function handleCreateTopic(e) {
            e.preventDefault();
            const text = document.getElementById('topic-text').value.trim();
            const imageFile = window.convertedGifFile || document.getElementById('topic-image').files[0];
            const allowDownload = document.getElementById('topic-allow-download').checked;
            const btn = document.getElementById('submit-topic-btn');

            if (!text) return;

            btn.disabled = true;
            btn.innerHTML = `<span class="animate-pulse">Publishing...</span>`;

            try {
                const fd = new FormData();
                fd.append('text', text);
                fd.append('location', detectedLocation);
                fd.append('allow_download', allowDownload);
                if (imageFile) {
                    fd.append('image', imageFile);
                }

                const res = await fetch('/api/topics', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    document.getElementById('topic-text').value = '';
                    clearImagePreview();
                    fetchFeed();
                    fetchTrending();
                } else {
                    alert(data.detail || "Error publishing topic.");
                }
            } catch (err) {
                console.error("Create topic error:", err);
                alert("Failed to submit.");
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>Share Say</span><i data-lucide="send" class="h-4 w-4"></i>`;
                lucide.createIcons();
            }
        }

        async function fetchFeed() {
            const icon = document.getElementById('feed-reload-icon');
            if (icon) icon.classList.add('animate-spin');

            try {
                const res = await fetch('/api/topics');
                const data = await res.json();

                if (res.ok && data.success) {
                    window.activeTopicsList = data.topics; // Store topics globally for JSON/CSV export
                    window.loadedTopicIds = data.topics.map(t => t.id);
                    const pill = document.getElementById("new-topics-pill");
                    if (pill) pill.classList.add("hidden");
                    renderFeed(data.topics);
                } else {
                    console.error("Failed to load feed");
                }
            } catch (err) {
                console.error("Feed fetch error:", err);
            } finally {
                if (icon) icon.classList.remove('animate-spin');
            }
        }

        function buildTopicHTML(topic, isHotTake = false) {
            const imageTag = topic.image_url ? `
                <div class="my-4 rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
                    <img src="${topic.image_url}" alt="Say image" class="w-full max-h-96 object-cover opacity-90 hover:opacity-100 transition duration-300">
                </div>
            ` : '';

            const locationTag = '';

            const progressColor = isHotTake
                ? 'from-amber-400 via-orange-500 to-rose-500'
                : topic.progress_percent === 100
                    ? 'from-amber-400 to-rose-500'
                    : 'from-indigo-500 to-fuchsia-500';

            const borderStyle = isHotTake
                ? 'border-2 border-amber-500/80 shadow-2xl shadow-amber-500/10'
                : 'border border-slate-800/80 shadow-xl';

            // Comments rendering in WhatsApp alternating style with replies
            const commentsHtml = topic.comments.map((c, idx) => {
                const isEven = (idx % 2 === 0);
                const alignmentClass = isEven ? 'justify-start' : 'justify-end';
                const bubbleBg = isEven ? 'bg-slate-800/80 border-slate-700/60' : 'bg-emerald-950/40 border-emerald-800/50';
                const roundedClass = isEven ? 'rounded-r-2xl rounded-bl-2xl' : 'rounded-l-2xl rounded-br-2xl';
                const borderHighlight = c.is_pinned
                    ? 'ring-2 ring-amber-500 border-amber-500 shadow-lg shadow-amber-500/10'
                    : 'border border-slate-800/60';

                // Pin label if pinned
                const pinHeader = c.is_pinned ? `
                    <div class="flex items-center space-x-1 text-amber-400 text-[10px] font-bold uppercase tracking-wider mb-1.5">
                        <i data-lucide="pin" class="h-3.5 w-3.5 fill-amber-400"></i>
                        <span>📌 Pinned (Most Discussed • ${c.replies_count} replies)</span>
                    </div>
                ` : '';

                // Build replies rendering
                const repliesHtml = c.replies && c.replies.length > 0 ? `
                    <div class="mt-3 pl-3.5 border-l-2 border-indigo-500/40 space-y-2">
                        ${c.replies.map(r => {
                            const isReplyOwner = currentUser && r.author && currentUser.id === r.author.id;
                            const replyActions = isReplyOwner ? `
                                <div class="flex items-center space-x-1">
                                    <button onclick="editComment(${r.id})" class="text-slate-400 hover:text-indigo-400 transition p-0.5" title="Edit Reply">
                                        <i data-lucide="edit-3" class="h-3 w-3"></i>
                                    </button>
                                    <button onclick="deleteComment(${r.id})" class="text-slate-400 hover:text-red-400 transition p-0.5" title="Delete Reply">
                                        <i data-lucide="trash-2" class="h-3 w-3"></i>
                                    </button>
                                </div>
                            ` : '';
                            return `
                                <div class="bg-slate-900/80 border border-slate-800/60 p-2.5 rounded-xl space-y-1">
                                    <div class="flex items-center justify-between gap-2">
                                        <span class="font-bold text-slate-300 text-xs cursor-help border-b border-dashed border-slate-700" title="Belief: ${escapeHTML(r.author.belief || 'None')}">@${escapeHTML(r.author.username)}</span>
                                        ${replyActions}
                                    </div>
                                    <p class="text-xs text-slate-300 leading-relaxed">${escapeHTML(r.text)}</p>
                                </div>
                            `;
                        }).join('')}
                    </div>
                ` : '';

                const isCommentOwner = currentUser && c.author && currentUser.id === c.author.id;
                const commentActions = isCommentOwner ? `
                    <div class="flex items-center space-x-1">
                        <button onclick="editComment(${c.id})" class="text-slate-400 hover:text-indigo-400 transition p-0.5" title="Edit Comment">
                            <i data-lucide="edit-3" class="h-3 w-3"></i>
                        </button>
                        <button onclick="deleteComment(${c.id})" class="text-slate-400 hover:text-red-400 transition p-0.5" title="Delete Comment">
                            <i data-lucide="trash-2" class="h-3 w-3"></i>
                        </button>
                    </div>
                ` : '';

                return `
                    <div class="w-full flex ${alignmentClass} my-3">
                        <div class="max-w-[85%] w-full sm:max-w-[75%] ${bubbleBg} ${borderHighlight} ${roundedClass} p-4 space-y-1.5">

                            <!-- Pin status if applicable -->
                            ${pinHeader}

                            <!-- Header -->
                            <div class="flex items-center justify-between gap-2">
                                <span class="font-bold text-slate-200 text-xs cursor-help border-b border-dashed border-slate-700" title="Belief: ${escapeHTML(c.author.belief || 'None')}">@${escapeHTML(c.author.username)}</span>
                                ${commentActions}
                            </div>

                            <!-- Comment Text -->
                            <p class="text-sm text-slate-200 font-normal leading-relaxed">${escapeHTML(c.text)}</p>

                            <!-- Nested Replies List -->
                            ${repliesHtml}

                            <!-- Actions & Reply Form Toggle -->
                            <div class="flex items-center justify-between pt-1 text-[11px] text-slate-400">
                                <span class="text-[10px] text-slate-500">${c.replies_count} replies</span>
                                <button onclick="toggleReplyForm(${topic.id}, ${c.id})" class="text-indigo-400 hover:text-indigo-300 font-bold transition flex items-center space-x-1" title="Reply to this comment">
                                    <i data-lucide="message-square" class="h-3.5 w-3.5"></i>
                                    <span>Reply</span>
                                </button>
                            </div>

                            <!-- Inline Reply Form -->
                            <form id="reply-form-${topic.id}-${c.id}" onsubmit="handleCreateNestedComment(${topic.id}, ${c.id}, event)" class="hidden mt-2 flex gap-1.5 pt-2 border-t border-slate-800/40">
                                <input type="text" id="reply-input-${topic.id}-${c.id}" required placeholder="Reply to @${escapeHTML(c.author.username)}..." class="block w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl focus:border-indigo-500 text-xs outline-none text-white">
                                <button type="submit" class="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-semibold shrink-0">Reply</button>
                            </form>

                        </div>
                    </div>
                `;
            }).join('');

            const elementId = isHotTake ? `hot-take-card-${topic.id}` : `topic-card-${topic.id}`;
            const countdownId = isHotTake ? `hot-take-countdown-${topic.id}` : `countdown-${topic.id}`;

            const isOwner = currentUser && topic.author && currentUser.id === topic.author.id;
            let downloadControls = '';
            if (topic.allow_download) {
                downloadControls = `
                    <button onclick="downloadTopicJSON(${topic.id})" class="p-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-750 hover:border-slate-600 rounded-lg text-slate-300 hover:text-indigo-400 transition shadow" title="Download Conversation (JSON)">
                        <i data-lucide="file-json" class="h-4 w-4"></i>
                    </button>
                    <button onclick="downloadTopicCSV(${topic.id})" class="p-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-750 hover:border-slate-600 rounded-lg text-slate-300 hover:text-emerald-400 transition shadow" title="Download Conversation (CSV)">
                        <i data-lucide="file-spreadsheet" class="h-4 w-4"></i>
                    </button>
                `;
                if (isOwner) {
                    downloadControls += `
                        <button onclick="toggleTopicDownload(${topic.id}, false)" class="p-1.5 bg-slate-800 hover:bg-red-950 border border-slate-750 hover:border-red-900 rounded-lg text-red-400 transition shadow" title="Disable downloads (Owner Control)">
                            <i data-lucide="unlock" class="h-4 w-4"></i>
                        </button>
                    `;
                }
            } else {
                downloadControls = `
                    <div class="text-[10px] text-slate-500 font-semibold uppercase tracking-wider bg-slate-950/60 border border-slate-800/60 py-1.5 px-2 rounded-lg flex items-center gap-1 select-none" title="Download records disabled by topic creator">
                        <i data-lucide="lock" class="h-3 w-3 text-red-500"></i>
                        <span>Locked</span>
                    </div>
                `;
                if (isOwner) {
                    downloadControls += `
                        <button onclick="toggleTopicDownload(${topic.id}, true)" class="p-1.5 bg-slate-800 hover:bg-emerald-950 border border-slate-750 hover:border-emerald-900 rounded-lg text-emerald-400 transition shadow" title="Enable downloads (Owner Control)">
                            <i data-lucide="lock-keyhole" class="h-4 w-4"></i>
                        </button>
                    `;
                }
            }

            return `
                <div class="bg-slate-900 ${borderStyle} rounded-2xl overflow-hidden relative" id="${elementId}">

                    <!-- ENGAGEMENT PROGRESS BAR AT TOP OF CARD -->
                    <div class="w-full h-2 bg-slate-950 relative overflow-hidden" title="Engagement score: ${topic.progress_percent}% relative to peak discussion">
                        <div class="h-full bg-gradient-to-r ${progressColor} transition-all duration-500" style="width: ${topic.progress_percent}%"></div>
                    </div>

                    <div class="p-6 space-y-4">
                        <!-- Card Header (Creator Identity & Location & Expiry countdown) -->
                        <div class="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/60">
                            <div class="flex items-center space-x-2.5">
                                <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-slate-800 to-slate-700 border border-slate-600 flex items-center justify-center font-bold text-indigo-400">
                                    @
                                </div>
                                <div>
                                    <div class="text-sm font-bold text-white cursor-help border-b border-dashed border-slate-700" title="Belief: ${escapeHTML(topic.author.belief || 'None')}">@${escapeHTML(topic.author.username)}</div>
                                </div>
                            </div>

                            <div class="flex items-center space-x-2">
                                ${locationTag}
                                ${downloadControls}
                                <div class="flex items-center space-x-1 text-xs text-indigo-300 font-semibold bg-indigo-950/40 border border-indigo-900/30 rounded-lg py-1 px-2">
                                    <i data-lucide="clock" class="h-3.5 w-3.5 text-indigo-400 animate-pulse"></i>
                                    <span id="${countdownId}" data-seconds="${topic.time_left_seconds}">Calculating...</span>
                                </div>
                                ${isOwner ? `
                                    <div class="flex items-center space-x-1 border-l border-slate-800 pl-2">
                                        <button onclick="editTopic(${topic.id})" class="p-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 hover:text-indigo-400 transition" title="Edit Conversation">
                                            <i data-lucide="edit-3" class="h-3.5 w-3.5"></i>
                                        </button>
                                        <button onclick="deleteTopic(${topic.id})" class="p-1 bg-slate-800 hover:bg-red-950 border border-slate-700 hover:border-red-900 rounded-lg text-slate-300 hover:text-red-400 transition" title="Delete Conversation">
                                            <i data-lucide="trash-2" class="h-3.5 w-3.5"></i>
                                        </button>
                                    </div>
                                ` : ''}
                            </div>
                        </div>

                        <!-- Say Text -->
                        <p class="text-base text-slate-200 font-normal leading-relaxed whitespace-pre-line">${escapeHTML(topic.text)}</p>

                        <!-- Say Image -->
                        ${imageTag}

                        <!-- Engagement Metrics Info -->
                        <div class="flex items-center justify-between pt-1 text-xs text-slate-400">
                            <div class="flex items-center space-x-2 font-medium">
                                <i data-lucide="message-square" class="h-4 w-4 text-indigo-400"></i>
                                <span class="text-white">${topic.comments_count}</span>
                                <span>comments</span>
                            </div>
                            <div class="flex items-center space-x-1 text-indigo-300 font-semibold">
                                <span>Engagement:</span>
                                <span class="bg-indigo-950 border border-indigo-800/30 px-1.5 py-0.5 rounded text-indigo-300">${topic.progress_percent}%</span>
                            </div>
                        </div>

                        <!-- Comments Section -->
                        <div class="border-t border-slate-800/60 pt-4 space-y-3.5">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Replies</h4>

                            <div class="space-y-2.5 max-h-60 overflow-y-auto pr-1">
                                ${commentsHtml || `<p class="text-xs text-slate-500 italic py-2">No reactions yet. Join the conversation below!</p>`}
                            </div>

                            <!-- Add comment form -->
                            <form onsubmit="handleCreateComment(${topic.id}, event)" class="flex gap-2 pt-2">
                                <input type="text" id="comment-input-${isHotTake ? 'hot-' : ''}${topic.id}" required placeholder="Add your reactions anonymously..." class="block w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-white placeholder-slate-500 text-xs transition duration-150 outline-none">
                                <button type="submit" class="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-xl font-semibold text-xs shadow transition duration-150 flex items-center justify-center space-x-1 shrink-0">
                                    <span>Reply</span>
                                    <i data-lucide="corner-down-left" class="h-3.5 w-3.5"></i>
                                </button>
                            </form>
                        </div>

                    </div>
                </div>
            `;
        }

        function renderFeed(topics) {
            const feedContainer = document.getElementById('feed-container');
            const hotTakeContainer = document.getElementById('hot-take-container');
            const hotTakeOuter = document.getElementById('hot-take-outer-container');

            // Clear existing intervals to avoid memory leaks
            countdownIntervals.forEach(clearInterval);
            countdownIntervals = [];

            if (!topics || topics.length === 0) {
                hotTakeOuter.classList.add('hidden');
                feedContainer.innerHTML = `
                    <div class="text-center py-16 bg-slate-900 border border-slate-800/80 rounded-2xl">
                        <div class="inline-flex p-4 bg-slate-950 rounded-2xl border border-slate-800 mb-3 text-slate-500">
                            <i data-lucide="ghost" class="h-8 w-8"></i>
                        </div>
                        <h3 class="text-base font-semibold text-white">Silence...</h3>
                        <p class="text-sm text-slate-400 mt-1 max-w-sm mx-auto">Nobody has had their say yet, or everything has expired. Be the first to start the conversation!</p>
                    </div>
                `;
                lucide.createIcons();
                return;
            }

            // Define the "Hot Take" topic:
            // This is the active topic with the highest comment count.
            // If there's a tie, we take the one that is newer (first in array since they are sorted newest first).
            // It MUST have at least 1 comment to qualify, otherwise we don't pin anything yet, or we can pin the newest!
            // Let's pin the one with the highest comment count. If all have 0 comments, we don't pin any hot take yet,
            // OR we can pin the newest topic. Let's require at least 1 comment for a true "Hot Take" of the moment,
            // which encourages people to comment to crown the "Hot Take of the Moment"! This is a very game-like, high-retention mechanic!
            // If all have 0 comments, we can just hide the "Hot Take" container. Let's do that.
            let hotTakeTopic = null;
            let highestComments = 0;

            for (const t of topics) {
                if (t.comments_count > highestComments) {
                    highestComments = t.comments_count;
                    hotTakeTopic = t;
                }
            }

            // Render Hot Take if found
            if (hotTakeTopic) {
                hotTakeOuter.classList.remove('hidden');
                hotTakeContainer.innerHTML = buildTopicHTML(hotTakeTopic, true);
                startCountdownTimer(hotTakeTopic.id, hotTakeTopic.time_left_seconds, true);
            } else {
                hotTakeOuter.classList.add('hidden');
            }

            // Render remaining topics in the normal feed (excluding the hot take topic to avoid redundancy)
            const regularTopics = topics.filter(t => !hotTakeTopic || t.id !== hotTakeTopic.id);

            if (regularTopics.length === 0 && hotTakeTopic) {
                feedContainer.innerHTML = `
                    <div class="text-center py-6 border border-slate-800 border-dashed rounded-2xl text-xs text-slate-500">
                        The only active topic is crowned as the Hot Take above! 🔥
                    </div>
                `;
            } else {
                feedContainer.innerHTML = regularTopics.map(topic => buildTopicHTML(topic, false)).join('');
                regularTopics.forEach(topic => {
                    startCountdownTimer(topic.id, topic.time_left_seconds, false);
                });
            }

            lucide.createIcons();
        }

        function startCountdownTimer(topicId, totalSeconds, isHotTake = false) {
            const idString = isHotTake ? `hot-take-countdown-${topicId}` : `countdown-${topicId}`;
            const el = document.getElementById(idString);
            if (!el) return;

            let remaining = totalSeconds;

            function update() {
                if (remaining <= 0) {
                    el.innerText = "Expired";
                    el.className = "text-red-400 font-semibold flex items-center space-x-1";
                    setTimeout(fetchFeed, 3000);
                    return;
                }

                const hours = Math.floor(remaining / 3600);
                const minutes = Math.floor((remaining % 3600) / 60);
                const seconds = remaining % 60;

                el.innerText = `${hours}h ${minutes}m ${seconds}s`;
                remaining--;
            }

            update();
            const interval = setInterval(update, 1000);
            countdownIntervals.push(interval);
        }

        async function handleCreateComment(topicId, e) {
            e.preventDefault();

            // Try to pull comment from regular feed input or hot take input
            let input = document.getElementById(`comment-input-${topicId}`);
            if (!input) {
                input = document.getElementById(`comment-input-hot-${topicId}`);
            }

            if (!input) return;
            const text = input.value.trim();
            if (!text) return;

            try {
                const fd = new FormData();
                fd.append('text', text);
                fd.append('location', detectedLocation);

                const res = await fetch(`/api/topics/${topicId}/comments`, {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    input.value = '';
                    fetchFeed();
                    fetchTrending();
                } else {
                    alert(data.detail || "Failed to submit reaction.");
                }
            } catch (err) {
                console.error("Create comment error:", err);
                alert("Failed to send reply.");
            }
        }

        function toggleReplyForm(topicId, commentId) {
            const form = document.getElementById(`reply-form-${topicId}-${commentId}`);
            if (form) {
                form.classList.toggle('hidden');
                const input = document.getElementById(`reply-input-${topicId}-${commentId}`);
                if (!form.classList.contains('hidden') && input) {
                    input.focus();
                }
            }
        }

        async function handleCreateNestedComment(topicId, commentId, e) {
            e.preventDefault();
            const input = document.getElementById(`reply-input-${topicId}-${commentId}`);
            if (!input) return;
            const text = input.value.trim();
            if (!text) return;

            try {
                const fd = new FormData();
                fd.append('text', text);
                fd.append('parent_id', commentId);
                fd.append('location', detectedLocation);

                const res = await fetch(`/api/topics/${topicId}/comments`, {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    input.value = '';
                    fetchFeed();
                    fetchTrending();
                } else {
                    alert(data.detail || "Failed to submit reply.");
                }
            } catch (err) {
                console.error("Create nested comment error:", err);
                alert("Failed to send reply.");
            }
        }


        // --- TRENDING LIST ---
        async function fetchTrending() {
            try {
                const res = await fetch('/api/trending');
                const data = await res.json();

                if (res.ok && data.success) {
                    renderTrending(data.trending);
                }
            } catch (err) {
                console.error("Trending error:", err);
            }
        }

        function renderTrending(trendingList) {
            const container = document.getElementById('trending-container');
            if (!trendingList || trendingList.length === 0) {
                container.innerHTML = `
                    <div class="text-xs text-slate-500 italic text-center py-4">
                        No trending topics available.
                    </div>
                `;
                return;
            }

            container.innerHTML = trendingList.map((item, index) => {
                const badgeColor = index === 0
                    ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
                    : index === 1
                        ? 'bg-slate-300/10 text-slate-300 border-slate-300/20'
                        : 'bg-slate-800 text-slate-400 border-slate-700/50';

                return `
                    <div class="bg-slate-950/40 hover:bg-slate-950 border border-slate-800 p-3 rounded-xl transition duration-150 flex items-start space-x-3 cursor-pointer" onclick="scrollToTopic(${item.id})">
                        <span class="w-6 h-6 shrink-0 rounded-lg border flex items-center justify-center font-bold text-xs ${badgeColor}">
                            ${index + 1}
                        </span>
                        <div class="space-y-1 overflow-hidden flex-grow">
                            <p class="text-xs font-semibold text-slate-200 truncate">${escapeHTML(item.text)}</p>
                            <div class="flex items-center justify-between text-[10px] text-slate-500">
                                <span>by @${escapeHTML(item.author.username)}</span>
                                <span class="flex items-center gap-1 font-medium text-indigo-400">
                                    <i data-lucide="message-square" class="h-3 w-3"></i>
                                    <span>${item.comments_count} replies</span>
                                </span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            lucide.createIcons();
        }

        function scrollToTopic(id) {
            let el = document.getElementById(`topic-card-${id}`);
            if (!el) {
                el = document.getElementById(`hot-take-card-${id}`);
            }
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Add a brief highlight effect
                el.classList.add('ring-2', 'ring-indigo-500');
                setTimeout(() => el.classList.remove('ring-2', 'ring-indigo-500'), 2500);
            }
        }

        async function toggleTopicDownload(topicId, allow) {
            try {
                const fd = new FormData();
                fd.append('allow_download', allow ? 'true' : 'false');
                const res = await fetch(`/api/topics/${topicId}`, {
                    method: 'PUT',
                    body: fd
                });
                const data = await res.json();
                if (data.success) {
                    await fetchFeed();
                    if (typeof fetchTrending === 'function') fetchTrending();
                } else {
                    alert("Error: " + (data.detail || data.message));
                }
            } catch (err) {
                console.error("Toggle downloads failed:", err);
                alert("Failed to toggle downloads option.");
            }
        }

        async function editTopic(topicId) {
            const topic = (window.activeTopicsList || []).find(t => t.id === topicId);
            if (!topic) return;

            const newText = prompt("Edit your conversation:", topic.text);
            if (newText === null) return;
            const trimmed = newText.trim();
            if (!trimmed) {
                alert("Conversation text cannot be empty.");
                return;
            }

            try {
                const fd = new FormData();
                fd.append('text', trimmed);
                const res = await fetch(`/api/topics/${topicId}`, {
                    method: 'PUT',
                    body: fd
                });
                const data = await res.json();
                if (data.success) {
                    await fetchFeed();
                    if (typeof fetchTrending === 'function') fetchTrending();
                } else {
                    alert("Error: " + (data.detail || data.message));
                }
            } catch (err) {
                console.error("Edit conversation failed:", err);
                alert("Failed to edit conversation.");
            }
        }

        async function deleteTopic(topicId) {
            if (!confirm("Are you sure you want to delete this conversation? This will permanently remove all of its comments and replies.")) return;

            try {
                const res = await fetch(`/api/topics/${topicId}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    await fetchFeed();
                    if (typeof fetchTrending === 'function') fetchTrending();
                } else {
                    alert("Error: " + (data.detail || data.message));
                }
            } catch (err) {
                console.error("Delete conversation failed:", err);
                alert("Failed to delete conversation.");
            }
        }

        async function editComment(commentId) {
            let currentText = "";
            for (let t of window.activeTopicsList || []) {
                for (let c of t.comments || []) {
                    if (c.id === commentId) {
                        currentText = c.text;
                        break;
                    }
                    for (let r of c.replies || []) {
                        if (r.id === commentId) {
                            currentText = r.text;
                            break;
                        }
                    }
                }
            }

            const newText = prompt("Edit your reaction:", currentText);
            if (newText === null) return;
            const trimmed = newText.trim();
            if (!trimmed) {
                alert("Reaction text cannot be empty.");
                return;
            }

            try {
                const fd = new FormData();
                fd.append('text', trimmed);
                const res = await fetch(`/api/comments/${commentId}`, {
                    method: 'PUT',
                    body: fd
                });
                const data = await res.json();
                if (data.success) {
                    await fetchFeed();
                    if (typeof fetchTrending === 'function') fetchTrending();
                } else {
                    alert("Error: " + (data.detail || data.message));
                }
            } catch (err) {
                console.error("Edit comment failed:", err);
                alert("Failed to edit comment.");
            }
        }

        async function deleteComment(commentId) {
            if (!confirm("Are you sure you want to delete this reaction? This will permanently remove it.")) return;

            try {
                const res = await fetch(`/api/comments/${commentId}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    await fetchFeed();
                    if (typeof fetchTrending === 'function') fetchTrending();
                } else {
                    alert("Error: " + (data.detail || data.message));
                }
            } catch (err) {
                console.error("Delete comment failed:", err);
                alert("Failed to delete reaction.");
            }
        }

        // --- CONVERSATION EXPORTS (ANONYMIZED RECORDS) ---
        function downloadTopicJSON(topicId) {
            const topic = (window.activeTopicsList || []).find(t => t.id === topicId);
            if (!topic) {
                alert("Topic data not found.");
                return;
            }

            // Securely scrub usernames of authors and commenters
            const scrubbedData = {
                topic_id: topic.id,
                text: topic.text,
                created_at: topic.created_at,
                expires_at: topic.expires_at,
                author: {
                    username: "Anonymized User",
                    belief: topic.author.belief || "None"
                },
                comments: (topic.comments || []).map(c => ({
                    id: c.id,
                    text: c.text,
                    created_at: c.created_at,
                    author: {
                        username: "Anonymized User",
                        belief: c.author.belief || "None"
                    },
                    replies: (c.replies || []).map(r => ({
                        id: r.id,
                        text: r.text,
                        created_at: r.created_at,
                        author: {
                            username: "Anonymized User",
                            belief: r.author.belief || "None"
                        }
                    }))
                }))
            };

            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(scrubbedData, null, 2));
            const dlAnchorElem = document.createElement('a');
            dlAnchorElem.setAttribute("href",     dataStr);
            dlAnchorElem.setAttribute("download", `conversation_${topicId}.json`);
            dlAnchorElem.click();
        }

        function downloadTopicCSV(topicId) {
            const topic = (window.activeTopicsList || []).find(t => t.id === topicId);
            if (!topic) {
                alert("Topic data not found.");
                return;
            }

            // Create CSV rows securely scrubbing all names/usernames
            let csvRows = [];
            csvRows.push("Type,ID,ParentID,Text,Created_At,Author,Belief");

            // Topic row
            csvRows.push(`Topic,${topic.id},,"${topic.text.replace(/"/g, '""')}",${topic.created_at},Anonymized User,"${(topic.author.belief || '').replace(/"/g, '""')}"`);

            // Comments and nested replies
            (topic.comments || []).forEach(c => {
                csvRows.push(`Comment,${c.id},,"${c.text.replace(/"/g, '""')}",${c.created_at},Anonymized User,"${(c.author.belief || '').replace(/"/g, '""')}"`);

                (c.replies || []).forEach(r => {
                    csvRows.push(`Reply,${r.id},${c.id},"${r.text.replace(/"/g, '""')}",${r.created_at},Anonymized User,"${(r.author.belief || '').replace(/"/g, '""')}"`);
                });
            });

            const csvString = csvRows.join("\n");
            const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const dlAnchorElem = document.createElement('a');
            dlAnchorElem.setAttribute("href", url);
            dlAnchorElem.setAttribute("download", `conversation_${topicId}.csv`);
            dlAnchorElem.click();
            URL.revokeObjectURL(url);
        }


// --- Modal Identity Settings ---
function openSettingsModal() {
    if (!currentUser) {
        alert("Please login first to view or set your identity settings.");
        return;
    }
    const modal = document.getElementById("settings-modal");
    if (modal) {
        modal.classList.remove("hidden");
        document.getElementById("modal-username").value = currentUser.alias || "";
        document.getElementById("modal-belief").value = currentUser.belief || "";
        lucide.createIcons();
    }
}

function closeSettingsModal() {
    const modal = document.getElementById("settings-modal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

async function handleModalProfileUpdate(e) {
    if (e) e.preventDefault();
    const userVal = document.getElementById("modal-username").value.trim();
    const beliefVal = document.getElementById("modal-belief").value.trim();

    try {
        const fd = new FormData();
        fd.append("username", userVal);
        fd.append("belief", beliefVal);

        const res = await fetch("/api/auth/profile", {
            method: "POST",
            body: fd
        });
        const data = await res.json();

        if (res.ok && data.success) {
            currentUser = data.user;
            alert("Identity details updated successfully!");
            closeSettingsModal();
            // Refresh main screen displays
            showAppScreen();
        } else {
            alert(data.detail || "Failed to update profile.");
        }
    } catch (err) {
        console.error("Profile update error:", err);
        alert("Error connecting to server.");
    }
}


// --- Mobile Tab Switching (Twitter-Style) ---
let currentMobileTab = "feed";

function switchMobileTab(tab) {
    currentMobileTab = tab;
    const feedCol = document.getElementById("feed-column");
    const trendingCol = document.getElementById("trending-column");
    const tabFeedBtn = document.getElementById("mobile-tab-feed");
    const tabTrendingBtn = document.getElementById("mobile-tab-trending");

    if (tab === "feed") {
        if (feedCol) {
            feedCol.classList.remove("hidden");
            feedCol.classList.add("block");
        }
        if (trendingCol) {
            trendingCol.classList.remove("block");
            trendingCol.classList.add("hidden");
        }
        if (tabFeedBtn) {
            tabFeedBtn.classList.remove("text-slate-400");
            tabFeedBtn.classList.add("text-indigo-400");
        }
        if (tabTrendingBtn) {
            tabTrendingBtn.classList.remove("text-indigo-400");
            tabTrendingBtn.classList.add("text-slate-400");
        }
    } else if (tab === "trending") {
        if (feedCol) {
            feedCol.classList.remove("block");
            feedCol.classList.add("hidden");
        }
        if (trendingCol) {
            trendingCol.classList.remove("hidden");
            trendingCol.classList.add("block");
        }
        if (tabFeedBtn) {
            tabFeedBtn.classList.remove("text-indigo-400");
            tabFeedBtn.classList.add("text-slate-400");
        }
        if (tabTrendingBtn) {
            tabTrendingBtn.classList.remove("text-slate-400");
            tabTrendingBtn.classList.add("text-indigo-400");
        }
        if (typeof fetchTrending === "function") {
            fetchTrending();
        }
    }
    lucide.createIcons();
}


// --- Background Reload & Polling ---
window.loadedTopicIds = [];

async function startBackgroundPolling() {
    setInterval(async () => {
        const appScreen = document.getElementById("app-screen");
        // Only run polling if the user is authenticated and viewing the app screen
        if (appScreen && !appScreen.classList.contains("hidden")) {
            try {
                const res = await fetch("/api/topics");
                const data = await res.json();
                if (res.ok && data.success) {
                    const latestIds = data.topics.map(t => t.id);
                    // Check if there is any new topic ID not currently loaded
                    const hasNew = latestIds.some(id => !window.loadedTopicIds || !window.loadedTopicIds.includes(id));
                    if (hasNew) {
                        const pill = document.getElementById("new-topics-pill");
                        if (pill) {
                            pill.classList.remove("hidden");
                            lucide.createIcons();
                        }
                    }
                }
            } catch (err) {
                console.error("Background polling error:", err);
            }
        }
    }, 10000); // Poll every 10 seconds
}

function refreshFeedFromPill() {
    fetchFeed();
    // Scroll smoothly to top of the feed to see the new topics
    window.scrollTo({ top: 0, behavior: "smooth" });
}
