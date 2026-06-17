' =============================================================================
' _silent.vbs — Lanceur SILENCIEUX (aucune fenetre) pour les taches planifiees.
'
' Lance par wscript.exe (qui n'alloue PAS de console), il execute la commande
' passee en arguments avec un style de fenetre MASQUE (0). Resultat : zero flash
' de terminal, meme sous le Planificateur en session interactive — et sans avoir
' besoin de droits administrateur (contrairement au logon S4U).
'
' Usage (par le Planificateur) :
'   wscript.exe "_silent.vbs" "<exe>" <args...>
' Exemple :
'   wscript.exe "...\_silent.vbs" "pwsh.exe" -NoProfile -File "...\_etat_tache.ps1" -Perimetre "..."
' =============================================================================
Option Explicit
Dim sh, cmd, i, a
Set sh = CreateObject("WScript.Shell")
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
  a = WScript.Arguments(i)
  If InStr(a, " ") > 0 Then a = """" & a & """"   ' re-quoter les arguments contenant des espaces
  If i > 0 Then cmd = cmd & " "
  cmd = cmd & a
Next
' 0 = fenetre masquee ; True = ATTENDRE la fin du process.
' On attend volontairement : ainsi l'instance de tache reste vivante tant que la
' commande tourne. Indispensable si la commande est longue et SYNCHRONE (ex.
' transcription inline) -> sans attente, le Planificateur considererait la tache
' finie et tuerait le process detache. Pour une tache breve (etat) : ~1 s, sans
' impact.
sh.Run cmd, 0, True
