// ---- [BOOT] wizard-only entry point ----
window.setP=setP;window.bSetL=bSetL;window.chSet=chSet;window.sabSet=sabSet;window.wpnUndo=wpnUndo;window.wpnClear=wpnClear;window.renderStepUI=renderStepUI;window.renderWiz=renderWiz;window.wizNext=wizNext;window.wizPrev=wizPrev;window.gotoStep=gotoStep;window.openJson=openJson;
window.trigToggle=trigToggle;window.trigSet=trigSet;window.trigCooldownSet=trigCooldownSet;window.statSet=statSet;
window.saveActionAsMove=saveActionAsMove;window.deleteMove=deleteMove;window.exportMoves=exportMoves;window.importMoves=importMoves;window.redrawMoveList=redrawMoveList;
rsz();bootWizard();requestAnimationFrame(tick);
