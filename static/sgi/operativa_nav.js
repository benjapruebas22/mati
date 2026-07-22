(function () {
  const TOKEN = '__SEDE__';

  function getSelectedCode(shell) {
    const dataCode = String(shell.dataset.selectedCode || '').trim().toUpperCase();
    if (dataCode) return dataCode;
    const activeNode = shell.querySelector('.sede-nav [data-code].active');
    return activeNode ? String(activeNode.dataset.code || '').trim().toUpperCase() : '';
  }

  function updateModuleLinks(shell, code) {
    const selectedCode = String(code || '').trim().toUpperCase();
    if (!selectedCode) return;
    shell.dataset.selectedCode = selectedCode;
    shell.querySelectorAll('.sede-nav [data-code]').forEach((node) => {
      const isActive = String(node.dataset.code || '').trim().toUpperCase() === selectedCode;
      node.classList.toggle('active', isActive);
      if (isActive) {
        node.setAttribute('aria-current', 'page');
      } else {
        node.removeAttribute('aria-current');
      }
    });
    shell.querySelectorAll('[data-href-template]').forEach((node) => {
      const template = String(node.dataset.hrefTemplate || '').trim();
      if (!template) return;
      node.setAttribute('href', template.replace(/__SEDE__/g, selectedCode));
    });
  }

  function attachShell(shell) {
    if (!shell || shell.dataset.operativaNavReady === '1') return;
    shell.dataset.operativaNavReady = '1';

    const initialCode = getSelectedCode(shell);
    if (initialCode) updateModuleLinks(shell, initialCode);

    shell.querySelectorAll('.sede-nav [data-code]').forEach((node) => {
      node.addEventListener('click', (event) => {
        const code = String(node.dataset.code || '').trim().toUpperCase();
        if (!code) return;
        event.preventDefault();
        updateModuleLinks(shell, code);
        shell.dispatchEvent(new CustomEvent('operativa-nav:select', {
          bubbles: true,
          detail: { code: code, shell: shell }
        }));
      });
    });
  }

  document.querySelectorAll('.operativa-nav-shell').forEach(attachShell);
})();
