# SKTFPLRAO*EURWBPGHTSDZ

from plover import system as _plover_system
from plover import translation as _plover_translation
from plover.steno import Stroke

def _patch_asterisk_undo():
    """
    Mantém o '*' funcionando simultaneamente como:

        *      -> undo
        PA*G   -> sufixo {^a}

    O problema é que, ao colocar '*' em SUFFIX_KEYS e criar
    a entrada "*" -> "{^a}", o Plover encontra "*" como uma
    tradução normal antes de processar UNDO_STROKE_STENO.

    Aqui interceptamos somente o stroke EXATAMENTE igual a '*'.
    Qualquer stroke que contenha outras teclas continua passando
    pelo mecanismo normal de sufixação do Plover.
    """

    translator_class = _plover_translation.Translator

    # Evita aplicar o patch duas vezes caso o módulo seja recarregado.
    if getattr(translator_class, '_portuguese_asterisk_undo_patch', False):
        return

    original_translate_stroke = translator_class.translate_stroke

    def translate_stroke_with_portuguese_asterisk(self, stroke):
        # Só interfere no sistema Português.
        #
        # É importante usar NAME para que esse patch não altere
        # o comportamento de outros sistemas do Plover.
        if (
            _plover_system.NAME == 'Portuguese Stenotype'
            and _plover_system.UNDO_STROKE_STENO == '*'
            and stroke.rtfcre == '*'
        ):
            macro = _plover_translation.Macro(
                'undo',
                stroke,
                '',
            )
            self.translate_macro(macro)
            return

        # Todo o restante permanece exatamente como no Plover.
        return original_translate_stroke(self, stroke)

    translator_class.translate_stroke = translate_stroke_with_portuguese_asterisk
    translator_class._portuguese_asterisk_undo_patch = True


def _patch_skfl_suffix():
    """
    Adiciona o modificador SKFL para transformar a tradução de um
    stroke em um sufixo.

    Prioridade:

        1. Entrada direta do stroke completo no dicionário.
        2. Caso não exista, remove SKFL.
        3. O stroke restante é processado pelo mecanismo NORMAL
           do Plover.
        4. O resultado desse processamento é transformado em sufixo.

    Exemplos:

        E
        -> e

        R/E
        -> relaciono e

        R/SKFLE
        -> relacione

        AR
        -> ar

        A*R
        -> ara

        R/SKFLA*R
        -> relacionara

    Restrições:

        - Entradas diretas do dicionário sempre têm prioridade.
        - SKFL sozinho não faz nada.
        - O stroke-base não pode conter S, K, F ou L.
        - Entradas diretas continuam podendo conter múltiplos strokes.
        - O fallback SKFL só trabalha sobre UM stroke.
    """

    translator_class = _plover_translation.Translator

    if getattr(translator_class, '_portuguese_skfl_suffix_patch', False):
        return

    original_translate_stroke = translator_class.translate_stroke

    def translate_stroke_with_skfl_suffix(self, stroke):

        # Só interfere no sistema Português.
        if _plover_system.NAME == 'Portuguese Stenotype':

            # =========================================================
            # 1. PRIORIDADE ABSOLUTA:
            #    entrada literal do stroke completo no dicionário
            # =========================================================

            try:
                direct_mapping = self.lookup((stroke,))
            except (KeyError, IndexError):
                direct_mapping = None

            if direct_mapping is not None:
                return original_translate_stroke(self, stroke)

            # =========================================================
            # 2. Verifica se o stroke contém SKFL
            # =========================================================

            keys = set(stroke.steno_keys)

            skfl_keys = {
                'S-',
                'K-',
                'F-',
                'L-',
            }

            if skfl_keys.issubset(keys):

                # Remove SKFL.
                remaining_keys = keys - skfl_keys

                # SKFL sozinho não possui stroke-base.
                if remaining_keys:

                    # =================================================
                    # 3. O stroke-base não pode possuir S/K/F/L
                    # =================================================

                    forbidden_keys = {
                        'S-',
                        'K-',
                        'F-',
                        'L-',
                        '-S',
                        '-K',
                        '-F',
                        '-L',
                    }

                    if not remaining_keys.intersection(forbidden_keys):

                        try:
                            base_stroke = type(stroke)(remaining_keys)
                        except (TypeError, ValueError):
                            base_stroke = None

                        if base_stroke is not None:

                            # =================================================
                            # 4. Primeiro tenta uma entrada literal do
                            #    stroke-base.
                            #
                            #    Ex.:
                            #        E -> e
                            # =================================================

                            try:
                                direct_base_mapping = self.lookup(
                                    (base_stroke,)
                                )
                            except (KeyError, IndexError):
                                direct_base_mapping = None

                            if direct_base_mapping is not None:

                                if (
                                    isinstance(direct_base_mapping, str)
                                    and direct_base_mapping
                                    and not direct_base_mapping.startswith('{')
                                ):
                                    suffix_mapping = (
                                        '{^' + direct_base_mapping + '}'
                                    )

                                    translation = (
                                        _plover_translation.Translation(
                                            [stroke],
                                            suffix_mapping,
                                        )
                                    )

                                    self.translate_translation(translation)
                                    return

                            # =================================================
                            # 5. Se não existe tradução direta para o
                            #    stroke-base, precisamos deixar o Plover
                            #    processá-lo NORMALMENTE.
                            #
                            #    Isso é importante para:
                            #
                            #        A*R -> ara
                            #
                            #    pois A*R pode depender da lógica de
                            #    SUFFIX_KEYS / autosuffix e não de uma
                            #    entrada literal "A*R" no dicionário.
                            # =================================================

                            # Criamos um Translator auxiliar somente para
                            # descobrir qual seria a tradução normal do
                            # stroke-base sem emitir o resultado.
                            #
                            # O método _lookup não deve ser chamado aqui,
                            # porque precisamos respeitar todas as regras
                            # normais de tradução do Plover.
                            try:
                                translations = self._translate_stroke(
                                    base_stroke
                                )
                            except AttributeError:
                                translations = None

                            if translations:

                                # Pega a tradução resultante.
                                mapping = translations[-1]

                                if (
                                    isinstance(mapping, str)
                                    and mapping
                                    and not mapping.startswith('{')
                                ):

                                    suffix_mapping = (
                                        '{^' + mapping + '}'
                                    )

                                    translation = (
                                        _plover_translation.Translation(
                                            [stroke],
                                            suffix_mapping,
                                        )
                                    )

                                    self.translate_translation(translation)
                                    return

        # Todo o restante continua exatamente como no Plover.
        return original_translate_stroke(self, stroke)

    translator_class.translate_stroke = translate_stroke_with_skfl_suffix
    translator_class._portuguese_skfl_suffix_patch = True
    
_patch_skfl_suffix()
_patch_asterisk_undo()

KEYS = (
    '#',
    'S-', 'K-', 'T-', 'F-', 'P-', 'L-', 'R-',
    'A-', 'O-',
    '*',
    '-E', '-U',
    '-R', '-W', '-B', '-P', '-G', '-H', '-T', '-S', '-D', '-Z',
)

IMPLICIT_HYPHEN_KEYS = ('A-', 'O-', '-E', '-U', '*')

SUFFIX_KEYS = ('-S', '-G', '-Z', '-D', '*')

NUMBER_KEY = '#'

NUMBERS = {
    'S-': '1-',
    'K-': '2-',
    'T-': '3-',
    'F-': '4-',
    'A-': '5-',
    'O-': '0-',
    '-R': '-6',
    '-B': '-7',
    '-G': '-8',
    '-T': '-9',
}

UNDO_STROKE_STENO = '*'

ORTHOGRAPHY_RULES = [
    # Collapse vowels in suffixes
    # como + endo = comendo
    # cai + iria = cairia
    (r'^(.+)[aeouiáéíóúãõâêôàü] \^ ([aeouiáéíóúãõâêôàü]\w*)$', r'\1\2'),
]

ORTHOGRAPHY_RULES_ALIASES = {}

ORTHOGRAPHY_WORDLIST = None

KEYMAPS = {
    'Gemini PR': {
        '#'         : ('#1', '#2', '#3', '#4', '#5', '#6', '#7', '#8', '#9', '#A', '#B', '#C'),
        'S-'        : ('S1-', 'S2-'),
        'K-'        : 'T-',
        'T-'        : 'K-',
        'F-'        : 'P-',
        'P-'        : 'W-',
        'L-'        : 'H-',
        'R-'        : 'R-',
        'A-'        : 'A-',
        'O-'        : 'O-',
        '*'         : ('*1', '*2', '*3', '*4'),
        '-E'        : '-E',
        '-U'        : '-U',
        '-R'        : '-F',
        '-W'        : '-R',
        '-B'        : '-P',
        '-P'        : '-B',
        '-G'        : '-L',
        '-H'        : '-G',
        '-T'        : '-T',
        '-S'        : '-S',
        '-D'        : '-D',
        '-Z'        : '-Z',
        'no-op'     : ('Fn', 'pwr', 'res1', 'res2'),
    },
    'Keyboard': {
        '#'         : ('1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='),
        'S-'        : ('a', 'q'),
        'K-'        : 'w',
        'T-'        : 's',
        'F-'        : 'e',
        'P-'        : 'd',
        'L-'        : 'r',
        'R-'        : 'f',
        'A-'        : 'c',
        'O-'        : 'v',
        '*'         : ('t', 'g', 'y', 'h'),
        '-E'        : 'n',
        '-U'        : 'm',
        '-R'        : 'u',
        '-W'        : 'j',
        '-B'        : 'i',
        '-P'        : 'k',
        '-G'        : 'o',
        '-H'        : 'l',
        '-T'        : 'p',
        '-S'        : ';',
        '-D'        : '[',
        '-Z'        : '\'',
        'arpeggiate': 'space',
        # Suppress adjacent keys to prevent miss-strokes.
        'no-op'     : ('z', 'x', 'b', ',', '.', '/', ']', '\\'),
    },
    'Passport': {
        '#'    : '#',
        'S-'   : ('S', 'C'),
        'K-'   : 'T',
        'T-'   : 'K',
        'F-'   : 'P',
        'P-'   : 'W',
        'L-'   : 'H',
        'R-'   : 'R',
        'A-'   : 'A',
        'O-'   : 'O',
        '*'    : ('~', '*'),
        '-E'   : 'E',
        '-U'   : 'U',
        '-R'   : 'F',
        '-W'   : 'Q',
        '-B'   : 'N',
        '-P'   : 'B',
        '-G'   : 'L',
        '-H'   : 'G',
        '-T'   : 'Y',
        '-S'   : 'X',
        '-D'   : 'D',
        '-Z'   : 'Z',
        'no-op': ('!', '^', '+'),
    },
    'Stentura': {
        '#'    : '#',
        'S-'   : 'S-',
        'K-'   : 'T-',
        'T-'   : 'K-',
        'F-'   : 'P-',
        'P-'   : 'W-',
        'L-'   : 'H-',
        'R-'   : 'R-',
        'A-'   : 'A-',
        'O-'   : 'O-',
        '*'    : '*',
        '-E'   : '-E',
        '-U'   : '-U',
        '-R'   : '-F',
        '-W'   : '-R',
        '-B'   : '-P',
        '-P'   : '-B',
        '-G'   : '-L',
        '-H'   : '-G',
        '-T'   : '-T',
        '-S'   : '-S',
        '-D'   : '-D',
        '-Z'   : '-Z',
        'no-op': '^',
    },
    'TX Bolt': {
        '#'    : '#',
        'S-'   : 'S-',
        'K-'   : 'T-',
        'T-'   : 'K-',
        'F-'   : 'P-',
        'P-'   : 'W-',
        'L-'   : 'H-',
        'R-'   : 'R-',
        'A-'   : 'A-',
        'O-'   : 'O-',
        '*'    : '*',
        '-E'   : '-E',
        '-U'   : '-U',
        '-R'   : '-F',
        '-W'   : '-R',
        '-B'   : '-P',
        '-P'   : '-B',
        '-G'   : '-L',
        '-H'   : '-G',
        '-T'   : '-T',
        '-S'   : '-S',
        '-D'   : '-D',
        '-Z'   : '-Z',
    },
    'Treal': {
        '#'    : ('#1', '#2', '#3', '#4', '#5', '#6', '#7', '#8', '#9', '#A', '#B'),
        'S-'   : ('S1-', 'S2-'),
        'K-'   : 'T-',
        'T-'   : 'K-',
        'F-'   : 'P-',
        'P-'   : 'W-',
        'L-'   : 'H-',
        'R-'   : 'R-',
        'A-'   : 'A-',
        'O-'   : 'O-',
        '*'    : ('*1', '*2'),
        '-E'   : '-E',
        '-U'   : '-U',
        '-R'   : '-F',
        '-W'   : '-R',
        '-B'   : '-P',
        '-P'   : '-B',
        '-G'   : '-L',
        '-H'   : '-G',
        '-T'   : '-T',
        '-S'   : '-S',
        '-D'   : '-D',
        '-Z'   : '-Z',
        'no-op': ('X1-', 'X2-', 'X3'),
    },
}

DICTIONARIES_ROOT = 'asset:plover:assets'
DEFAULT_DICTIONARIES = ()
