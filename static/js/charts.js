document.addEventListener("DOMContentLoaded", async function () {

    const categoryCanvas = document.getElementById("categoryChart");
    const monthlyCanvas = document.getElementById("monthlyChart");
    const weeklyCanvas = document.getElementById("weeklyChart");

    try {
        const response = await fetch("/api/chart-data");

        if (!response.ok) {
            throw new Error("Unable to load chart data");
        }

        const data = await response.json();

        // Category-wise expense chart
        if (categoryCanvas) {
            new Chart(categoryCanvas, {
                type: "doughnut",
                data: {
                    labels: data.category.labels,
                    datasets: [{
                        label: "Expenses",
                        data: data.category.values,
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        }

        // Monthly income and expense chart
        if (monthlyCanvas) {
            new Chart(monthlyCanvas, {
                type: "bar",
                data: {
                    labels: data.monthly.labels,
                    datasets: [
                        {
                            label: "Income",
                            data: data.monthly.income,
                            borderWidth: 1
                        },
                        {
                            label: "Expenses",
                            data: data.monthly.expenses,
                            borderWidth: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        // Weekly spending chart
        if (weeklyCanvas) {
            new Chart(weeklyCanvas, {
                type: "line",
                data: {
                    labels: data.weekly.labels,
                    datasets: [{
                        label: "Weekly Spending",
                        data: data.weekly.values,
                        tension: 0.3,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

    } catch (error) {
        console.error("Chart loading error:", error);
    }

});