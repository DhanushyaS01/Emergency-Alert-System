(function () {
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");
  const btnEmergency = document.getElementById("btn-emergency");
  const btnEmergencyLabel = document.getElementById("btn-emergency-label");
  const btnVoice = document.getElementById("btn-voice");
  const statusLine = document.getElementById("status-line");
  const locText = document.getElementById("loc-text");
  const voiceState = document.getElementById("voice-state");
  const smtpPill = document.getElementById("smtp-pill");
  const twilioPill = document.getElementById("twilio-pill");
  const waPill = document.getElementById("wa-pill");
  const camHint = document.getElementById("cam-hint");
  const emergencyMsg = document.getElementById("emergency-msg");

  let stream = null;
  let recognition = null;
  let voiceOn = false;
  let readyToSend = false;

  function setStatus(msg, kind) {
    statusLine.textContent = msg || "";
    statusLine.classList.remove("error", "ok");
    if (kind) statusLine.classList.add(kind);
  }

  function getEmergencyText() {
    var t = emergencyMsg && emergencyMsg.value ? emergencyMsg.value.trim() : "";
    return t || "I need help — this is an automated emergency alert.";
  }


  function waitForVideoDimensions(timeoutMs) {
    var limit = timeoutMs || 15000;
    return new Promise(function (resolve, reject) {
      function ok() {
        return video && video.videoWidth > 0 && video.videoHeight > 0;
      }
      if (ok()) {
        resolve();
        return;
      }
      var done = false;
      var to = setTimeout(function () {
        if (!done) {
          done = true;
          cleanup();
          reject(
            new Error(
              "Camera preview is not ready (video size still 0). Wait a moment and press SEND again."
            )
          );
        }
      }, limit);

      function cleanup() {
        clearTimeout(to);
        if (!video) return;
        video.removeEventListener("loadedmetadata", tryResolve);
        video.removeEventListener("loadeddata", tryResolve);
        video.removeEventListener("playing", tryResolve);
        video.removeEventListener("canplay", tryResolve);
      }

      function tryResolve() {
        if (done) return;
        if (ok()) {
          done = true;
          cleanup();
          resolve();
        }
      }

      video.addEventListener("loadedmetadata", tryResolve);
      video.addEventListener("loadeddata", tryResolve);
      video.addEventListener("playing", tryResolve);
      video.addEventListener("canplay", tryResolve);

      var rafId;
      function rafLoop() {
        if (done) return;
        tryResolve();
        if (!done) rafId = requestAnimationFrame(rafLoop);
      }
      rafId = requestAnimationFrame(rafLoop);
    });
  }

  function captureFrames(count, delayMs) {
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) {
      return Promise.reject(new Error("Camera not ready (no video size)."));
    }

    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const frames = [];

    function grabOne() {
      ctx.drawImage(video, 0, 0, w, h);
      frames.push(canvas.toDataURL("image/jpeg", 0.85));
    }

    grabOne();
    let i = 1;
    return new Promise(function (resolve, reject) {
      function tick() {
        if (i >= count) {
          resolve(frames);
          return;
        }
        setTimeout(function () {
          grabOne();
          i += 1;
          tick();
        }, delayMs);
      }
      tick();
    });
  }

  function getPosition() {
    return new Promise(function (resolve) {
      if (!navigator.geolocation) {
        resolve({ lat: "unavailable", lng: "unavailable" });
        return;
      }
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          resolve({
            lat: String(pos.coords.latitude),
            lng: String(pos.coords.longitude),
          });
        },
        function () {
          resolve({ lat: "denied_or_error", lng: "denied_or_error" });
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
      );
    });
  }

  async function startCamera() {
    if (stream) {
      stream.getTracks().forEach(function (t) {
        t.stop();
      });
      stream = null;
    }
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    await waitForVideoDimensions(15000);
    camHint.textContent = "Camera on — step 2 will capture photos when you send";
  }

  async function prepareAccess() {
    setStatus("Browser will ask for camera and location access…", "");
    btnEmergency.disabled = true;

    try {
      await startCamera();
    } catch (e) {
      camHint.textContent = "Camera blocked — allow camera to attach photos";
      setStatus(
        "Camera access is required for this app to attach images. Allow camera and try step 1 again.",
        "error"
      );
      btnEmergency.disabled = false;
      return;
    }

    var loc;
    try {
      loc = await getPosition();
    } catch (_) {
      loc = { lat: "denied_or_error", lng: "denied_or_error" };
    }

    locText.textContent =
      loc.lat === "denied_or_error" || loc.lat === "unavailable"
        ? "Not shared — enable location for GPS in alerts"
        : loc.lat + ", " + loc.lng;

    if (loc.lat === "denied_or_error" || loc.lat === "unavailable") {
      setStatus(
        "Camera is on. Location was not shared — enable location in the browser for GPS coordinates in your alert.",
        ""
      );
    } else {
      setStatus(
        "Access ready. Edit your message above if needed, then press “SEND” or say “help”.",
        "ok"
      );
    }

    readyToSend = true;
    if (btnEmergencyLabel) {
      btnEmergencyLabel.textContent = "\u2461 SEND EMERGENCY ALERT";
    }
    btnVoice.disabled = false;
    btnEmergency.disabled = false;
  }

  async function postEmergency(frames, pos) {
    var res = await fetch("/api/emergency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        images: frames,
        lat: pos.lat,
        lng: pos.lng,
        message: getEmergencyText(),
      }),
    });

    var text = await res.text();
    var data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      throw new Error(
        "Bad response from server (HTTP " +
          res.status +
          "). Is Flask running? First bytes: " +
          text.slice(0, 120)
      );
    }

    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Request failed (HTTP " + res.status + ")");
    }

    var detail =
      (data.message || "Alert sent.") +
      " Gender (estimate): " +
      (data.gender || "—") +
      ".";
    if (data.warnings && data.warnings.length) {
      detail += " " + data.warnings.join(" ");
    }
    setStatus(detail, "ok");
  }

  async function sendAlert() {
    if (!readyToSend) return;
    btnEmergency.disabled = true;
    setStatus("Sending alert…");

    var pos = await getPosition();
    locText.textContent =
      pos.lat === "denied_or_error" || pos.lat === "unavailable"
        ? "Not shared"
        : pos.lat + ", " + pos.lng;

    var frames = [];
    try {
      await waitForVideoDimensions(15000);
      frames = await captureFrames(3, 800);
    } catch (capErr) {
      var capMsg = capErr && capErr.message ? capErr.message : String(capErr);
      var fallback = window.confirm(
        capMsg +
          "\n\nSend the alert WITHOUT photos? (Location and your message will still be sent if email/SMS/WhatsApp is configured.)"
      );
      if (!fallback) {
        setStatus(capMsg, "error");
        btnEmergency.disabled = false;
        return;
      }
      frames = [];
    }

    try {
      await postEmergency(frames, pos);
    } catch (e) {
      setStatus(e.message || "Failed to send alert.", "error");
    } finally {
      btnEmergency.disabled = false;
    }
  }

  btnEmergency.addEventListener("click", async function () {
    if (!readyToSend) {
      await prepareAccess();
      return;
    }
    await sendAlert();
  });

  function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      if (btnVoice) btnVoice.disabled = true;
      voiceState.textContent = "Not supported";
      return;
    }
    recognition = new SR();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = function (ev) {
      if (!readyToSend) return;
      var text = "";
      for (var i = ev.resultIndex; i < ev.results.length; i++) {
        text += ev.results[i][0].transcript;
      }
      var lower = text.toLowerCase();
      if (/\bhelp\b/.test(lower)) {
        sendAlert();
      }
    };

    recognition.onerror = function () {
      if (voiceOn) voiceState.textContent = "Error — retry";
    };

    recognition.onend = function () {
      if (voiceOn) {
        try {
          recognition.start();
        } catch (_) {}
      }
    };
  }

  btnVoice.addEventListener("click", function () {
    if (!recognition || !readyToSend) return;
    voiceOn = !voiceOn;
    if (voiceOn) {
      try {
        recognition.start();
        voiceState.textContent = 'Listening for “help” (mic)';
        btnVoice.textContent = "Stop voice listening";
      } catch (_) {
        voiceOn = false;
        voiceState.textContent = "Could not start";
      }
    } else {
      recognition.stop();
      voiceState.textContent = "Off";
      btnVoice.textContent = "Enable “help” voice";
    }
  });

  function setPill(el, ok, okText, warnText) {
    if (!el) return;
    el.textContent = ok ? okText : warnText;
    el.classList.toggle("pill-ok", ok);
    el.classList.toggle("pill-warn", !ok);
  }

  fetch("/api/status")
    .then(function (r) {
      return r.json();
    })
    .then(function (s) {
      setPill(smtpPill, s.smtp_configured, "Email: ready", "Email: not set");
      setPill(twilioPill, s.twilio_configured, "SMS: ready", "SMS: not set");
      setPill(
        waPill,
        s.whatsapp_configured === true,
        "WhatsApp: ready",
        "WA: not set"
      );
      if (s.any_channel_configured === false) {
        setStatus(
          "No delivery channel configured. Copy .env.example to .env and set SMTP_* and/or Twilio. Restart python app.py.",
          "error"
        );
      }
    })
    .catch(function () {
      if (smtpPill) smtpPill.textContent = "Could not reach server";
      if (twilioPill) twilioPill.textContent = "";
      if (waPill) waPill.textContent = "";
      setStatus(
        "Cannot load /api/status — open this page via http://127.0.0.1:5000 (run python app.py first).",
        "error"
      );
    });

  locText.textContent = "Granted in step 1";

  initSpeech();
})();
