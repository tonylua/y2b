window.addEventListener('DOMContentLoaded', function() {
    let timer;
    const form = document.forms[0];
    const countdownElement = document.getElementById('countdown');

    // 自动提交函数
    function autoSubmit() {
        clearInterval(timer);
        form.submit();
    }

    // 倒计时更新函数
    function updateCountdown(seconds) {
        if (!countdownElement) return;
        countdownElement.textContent = `${seconds} 秒后自动提交`;
    }

    // 初始化倒计时
    updateCountdown(5);

    // 监听表单的交互事件来重置计时器
    ['click', 'mousemove', 'keydown', 'scroll'].forEach(eventType => {
        document.addEventListener(eventType, () => {
            clearInterval(timer);
            updateCountdown(5);
            timer = setTimeout(autoSubmit, 5000); // 5秒后调用autoSubmit
        });
    });

    // 开始倒计时
    timer = setTimeout(autoSubmit, 5000);
})