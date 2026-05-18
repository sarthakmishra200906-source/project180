const ESP32_BASE_URL = "http://192.168.4.1";

document.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement)) {
        return;
    }

    const action = target.dataset.action;
    if (!action) {
        return;
    }

    try {
        await fetch(`${ESP32_BASE_URL}/${action}`, { method: "POST" });
    } catch (error) {
        console.error("Failed to send control command", error);
    }
});
