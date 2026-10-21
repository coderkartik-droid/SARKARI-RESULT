const searchForm = document.querySelector("[data-search-form]");
const searchInput = document.querySelector("[data-search-input]");
const searchStatus = document.querySelector("[data-search-status]");
const noResults = document.querySelector("[data-no-results]");
const listingCards = [...document.querySelectorAll("[data-search-item]")];

document.querySelectorAll(".portal-menu-links a").forEach((link) => {
  link.addEventListener("click", () => {
    const href = link.getAttribute("href") || "";
    if (!href.startsWith("#")) return;
    const target = document.getElementById(href.slice(1));
    if (target) {
      target.setAttribute("tabindex", "-1");
      window.setTimeout(() => target.focus({ preventScroll: true }), 0);
    }
  });
});

if (searchForm && searchInput && searchStatus && noResults && listingCards.length) {
  function filterListings() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    let visibleCount = 0;

    listingCards.forEach((card) => {
      const haystack = `${card.textContent} ${card.dataset.category || ""}`.toLocaleLowerCase();
      const matches = !query || haystack.includes(query);
      card.hidden = !matches;
      if (matches) {
        visibleCount += 1;
      }
    });

    document.querySelectorAll("[data-listing-group]").forEach((section) => {
      section.hidden = !section.querySelector("[data-search-item]:not([hidden])");
    });

    noResults.hidden = visibleCount > 0;
    if (!query) {
      searchStatus.textContent = `Showing all ${visibleCount} listings.`;
    } else if (!visibleCount) {
      searchStatus.textContent = "";
      noResults.textContent = `No listings match “${searchInput.value.trim()}”. Try a different exam or keyword.`;
    } else {
      searchStatus.textContent = `Showing ${visibleCount} listing${visibleCount === 1 ? "" : "s"} for “${searchInput.value.trim()}”.`;
    }
  }

  function updateSearchUrl() {
    const url = new URL(window.location.href);
    const query = searchInput.value.trim();
    if (query) {
      url.searchParams.set("q", query);
    } else {
      url.searchParams.delete("q");
    }
    window.history.replaceState({}, "", url);
  }

  searchInput.addEventListener("input", () => {
    filterListings();
    updateSearchUrl();
  });
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    filterListings();
    updateSearchUrl();
  });
  filterListings();
}

// Mobile menu toggle functionality
const mobileMenuToggle = document.querySelector(".portal-mobile-menu-toggle");
const mobileMenuPanel = document.getElementById("mobile-menu-panel");

if (mobileMenuToggle && mobileMenuPanel) {
  mobileMenuToggle.addEventListener("click", () => {
    const isExpanded = mobileMenuToggle.getAttribute("aria-expanded") === "true";
    mobileMenuToggle.setAttribute("aria-expanded", !isExpanded);
    mobileMenuPanel.hidden = isExpanded;
    
    // Prevent body scroll when menu is open
    document.body.style.overflow = !isExpanded ? "hidden" : "";
  });

  // Close menu when clicking outside
  document.addEventListener("click", (event) => {
    if (!mobileMenuPanel.contains(event.target) && !mobileMenuToggle.contains(event.target)) {
      if (mobileMenuToggle.getAttribute("aria-expanded") === "true") {
        mobileMenuToggle.setAttribute("aria-expanded", "false");
        mobileMenuPanel.hidden = true;
        document.body.style.overflow = "";
      }
    }
  });

  // Close menu when clicking a nav link
  mobileMenuPanel.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      mobileMenuToggle.setAttribute("aria-expanded", "false");
      mobileMenuPanel.hidden = true;
      document.body.style.overflow = "";
    });
  });

  // Close menu on Escape key
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobileMenuToggle.getAttribute("aria-expanded") === "true") {
      mobileMenuToggle.setAttribute("aria-expanded", "false");
      mobileMenuPanel.hidden = true;
      document.body.style.overflow = "";
      mobileMenuToggle.focus();
    }
  });
}
