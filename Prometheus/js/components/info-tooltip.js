// ============ "?" 指标说明浮层组件 ============
// hover 时按视口边界动态纠正位置（避免被裁切看不全），且"图标+说明框"整体判定 hover 状态
// （鼠标从图标移向说明框内容区的路径上短暂"离开"不会被误关闭）。

export function setupInfoIconViewportClamp() {
  const margin = 8; // 说明框与视口边缘至少保留的间距（像素）
  document.querySelectorAll('.info-icon').forEach((icon) => {
    const tip = icon.querySelector('.tip');
    if (!tip) return;

    let closeTimer = null;

    function openTip() {
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }

      // 先重置成默认可见状态，才能测出这个说明框真实的宽高（display:none 时测不出尺寸）
      tip.style.display = 'block';
      tip.classList.add('js-positioned');
      tip.style.left = '0px';
      tip.style.top = '20px';
      tip.style.maxHeight = ''; // 先清空，按下面算出的可用空间重新设置

      const iconRect = icon.getBoundingClientRect();
      const tipRect = tip.getBoundingClientRect();

      // ---- 水平方向：以图标为中心水平居中，再钳制在视口左右边界内 ----
      let desiredLeft = iconRect.width / 2 - tipRect.width / 2;
      let absoluteLeft = iconRect.left + desiredLeft;
      if (absoluteLeft + tipRect.width > window.innerWidth - margin) {
        desiredLeft -= absoluteLeft + tipRect.width - (window.innerWidth - margin);
      }
      absoluteLeft = iconRect.left + desiredLeft;
      if (absoluteLeft < margin) {
        desiredLeft += margin - absoluteLeft;
      }
      tip.style.left = desiredLeft + 'px';

      // ---- 竖直方向：优先放下方；放不下就放上方；哪一侧都容纳不下时，选空间更大的一侧并限制可用高度 ----
      const spaceBelow = window.innerHeight - iconRect.bottom - margin - 6;
      const spaceAbove = iconRect.top - margin - 6;
      const desiredTop = 20;

      if (tipRect.height <= spaceBelow) {
        tip.style.top = desiredTop + 'px';
      } else if (tipRect.height <= spaceAbove) {
        tip.style.top = -(tipRect.height) - 6 + 'px';
      } else if (spaceBelow >= spaceAbove) {
        tip.style.top = desiredTop + 'px';
        tip.style.maxHeight = Math.max(120, spaceBelow) + 'px';
      } else {
        tip.style.top = -(iconRect.top - margin) + 'px';
        tip.style.maxHeight = Math.max(120, spaceAbove) + 'px';
      }
    }

    function scheduleClose() {
      if (closeTimer) clearTimeout(closeTimer);
      closeTimer = setTimeout(() => {
        tip.style.display = '';
      }, 150);
    }

    icon.addEventListener('mouseenter', openTip);
    icon.addEventListener('mouseleave', scheduleClose);
    tip.addEventListener('mouseenter', () => {
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    });
    tip.addEventListener('mouseleave', scheduleClose);
  });
}
