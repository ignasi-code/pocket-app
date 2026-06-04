# Store Backlog

- Persist dismissal of the shipping promo banner: once the user closes "Enjoy complimentary ground shipping on US orders $250+", do not show it again on later visits. Likely store a small `localStorage` flag and hide the banner on page load before paint where possible.
