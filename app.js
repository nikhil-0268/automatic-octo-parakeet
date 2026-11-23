/* Page behavior. No build step, dependencies, or network requests. */
"use strict";

initializeSlideshow();
initializeMobileMenu();
initializePickupDialog();

function initializeSlideshow() {
  const photos = [...document.querySelectorAll(".hero-photo")];
  const buttons = [...document.querySelectorAll(".slide-dot")];
  const toggle = document.getElementById("slideshowToggle");
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  let activeIndex = 0;
  let paused = motionPreference.matches;
  let intervalId;

  function showPhoto(index) {
    activeIndex = index;
    photos.forEach((photo, photoIndex) => {
      const active = photoIndex === index;
      photo.classList.toggle("active", active);
      photo.setAttribute("aria-hidden", String(!active));
    });
    buttons.forEach((button, buttonIndex) => {
      const active = buttonIndex === index;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", String(active));
    });
  }

  function updatePlayback() {
    window.clearInterval(intervalId);
    toggle.textContent = paused ? "Play slideshow" : "Pause slideshow";
    toggle.setAttribute("aria-pressed", String(paused));
    if (!paused && !document.hidden && photos.length > 1) {
      intervalId = window.setInterval(() => {
        showPhoto((activeIndex + 1) % photos.length);
      }, 5600);
    }
  }

  buttons.forEach((button, index) => {
    button.addEventListener("click", () => {
      showPhoto(index);
      updatePlayback();
    });
  });
  toggle.addEventListener("click", () => {
    paused = !paused;
    updatePlayback();
  });
  motionPreference.addEventListener("change", () => {
    paused = motionPreference.matches;
    updatePlayback();
  });
  document.addEventListener("visibilitychange", updatePlayback);
  showPhoto(0);
  updatePlayback();
}

function initializeMobileMenu() {
  const menu = document.getElementById("mobileNav");
  const toggle = document.getElementById("mobileToggle");
  const desktop = window.matchMedia("(min-width: 741px)");

  function setOpen(open) {
    menu.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  }

  toggle.addEventListener("click", () => {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });
  menu.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) setOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target) && !toggle.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.classList.contains("open")) {
      setOpen(false);
      toggle.focus();
    }
  });
  desktop.addEventListener("change", () => {
    if (desktop.matches) setOpen(false);
  });
}

function initializePickupDialog() {
  const dialog = document.getElementById("requestModal");
  const form = document.getElementById("pickupForm");
  const gateInput = document.getElementById("gateId");
  const wasteSelect = document.getElementById("wasteType");
  const status = document.getElementById("modalStatus");
  let opener;

  document.querySelectorAll("[data-request]").forEach((button) => {
    button.addEventListener("click", () => {
      opener = button;
      status.textContent = "";
      status.classList.remove("visible");
      gateInput.setCustomValidity("");
      document.body.classList.add("dialog-open");
      // Native dialog supplies focus containment and Escape handling.
      dialog.showModal();
      gateInput.focus();
    });
  });

  document.getElementById("closeModal").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    const bounds = dialog.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (event.target === dialog && outside) dialog.close();
  });
  dialog.addEventListener("close", () => {
    document.body.classList.remove("dialog-open");
    // Mobile request buttons live in a menu that closes on selection.
    if (opener?.getClientRects().length) opener.focus();
    else document.getElementById("mobileToggle").focus();
  });
  gateInput.addEventListener("input", () => gateInput.setCustomValidity(""));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const gateId = gateInput.value.trim().toUpperCase();
    gateInput.setCustomValidity(gateId ? "" : "Enter your registered Gate ID.");
    if (!form.reportValidity()) return;
    gateInput.value = gateId;
    // Select values are green / red / both; the data layer expects GREEN / RED / BOTH.
    const bagColor = wasteSelect.value.toUpperCase();
    status.replaceChildren();
    try {
      await window.tringggApi.requestPickup(gateId, bagColor);
      // textContent keeps user input as text, never executable HTML.
      status.append(`Pickup requested for ${gateId}. `);
      const link = document.createElement("a");
      link.href = `resident/dashboard.html?gate=${encodeURIComponent(gateId)}`;
      link.textContent = "Track it on your dashboard →";
      link.className = "modal-link";
      status.append(link);
    } catch (error) {
      status.textContent = error.message;
    }
    status.classList.add("visible");
  });
}
