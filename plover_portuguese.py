# SKTFPLRAO*EURWBPGHTSDZ

from plover import system as _plover_system
from plover import translation as _plover_translation
from plover.steno import Stroke
from plover import orthography as _plover_orthography
import re

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
    Adiciona SKFL como modificador de sufixo.

    Prioridade:

        1. Entrada literal do stroke completo no dicionário.
        2. Remove SKFL.
        3. Procura o stroke-base diretamente no dicionário.
        4. Caso o stroke-base use '*', resolve pelo mecanismo normal
           do Plover.
        5. Aplica as ORTHOGRAPHY_RULES gerais ao sufixo.
    
    A ortografia não depende do SKFL.

    Exemplos:

        E
            -> e

        SKFL E
            -> {^e}

        RAEUR -> {^rário}

        SKFLRAEUR
            -> {^rário}

        AR
            -> ar

        A*R
            -> ara

        SKFLA*R
            -> {^ara}

    Regra ortográfica:

        apareço + e
            -> aparece

        apareço + i
            -> apareci
    """

    translator_class = _plover_translation.Translator

    # Evita aplicar o patch duas vezes.
    if getattr(
        translator_class,
        '_portuguese_skfl_suffix_patch',
        False,
    ):
        return

    original_translate_stroke = (
        translator_class.translate_stroke
    )

    def _make_suffix(mapping):
        """
        Converte uma tradução em um sufixo.

        Exemplos:

            e
                -> {^e}

            {^rário}
                -> {^rário}

            ar {^a}
                -> {^ar}{^a}
        """

        if not isinstance(
            mapping,
            str,
        ) or not mapping:
            return None

        # Já é um sufixo.
        if mapping.startswith('{^'):
            return mapping

        # Texto normal + autosuffix.
        if '{^' in mapping:

            pos = mapping.find('{^')

            normal_part = mapping[:pos].rstrip()
            suffix_part = mapping[pos:]

            if normal_part:
                return (
                    '{^'
                    + normal_part
                    + '}'
                    + suffix_part
                )

            return suffix_part

        # Tradução normal.
        return '{^' + mapping + '}'

    def _apply_orthography(
        translator,
        suffix_mapping,
    ):
        """
        Aplica as ORTHOGRAPHY_RULES à palavra anterior.

        A regra é mantida completamente independente do SKFL.

        Exemplo:

            palavra:
                apareço

            suffix:
                {^e}

            regra:
                apareço ^ e -> aparece

        O resultado será:

            {#BackSpace}{^ce}

        Assim:

            apareço
              ↓
            apereço?  (não)
              ↓
            BackSpace remove o ç
              ↓
            {^ce} acrescenta "ce" sem espaço
              ↓
            aparece
        """

        if not isinstance(
            suffix_mapping,
            str,
        ):
            return suffix_mapping

        if not suffix_mapping:
            return suffix_mapping

        # =============================================================
        # Só trata um attach simples:
        #
        #     {^e}
        #     {^i}
        #     {^rário}
        #
        # Não interfere em traduções compostas como:
        #
        #     {^ar}{^a}
        # =============================================================

        if (
            not suffix_mapping.startswith('{^')
            or not suffix_mapping.endswith('}')
            or suffix_mapping.count('{^') != 1
        ):
            return suffix_mapping

        suffix = suffix_mapping[2:-1]

        if not suffix:
            return suffix_mapping

        # =============================================================
        # Recupera a tradução imediatamente anterior.
        # =============================================================

        previous_translations = (
            translator._state.translations
        )

        if not previous_translations:
            return suffix_mapping

        previous = previous_translations[-1]

        previous_text = previous.english

        if not isinstance(
            previous_text,
            str,
        ):
            return suffix_mapping

        if not previous_text:
            return suffix_mapping

        # =============================================================
        # Obtém somente a última palavra da tradução anterior.
        # =============================================================

        words = re.findall(
            r"[\wÀ-ÿ]+",
            previous_text,
            re.UNICODE,
        )

        if not words:
            return suffix_mapping

        previous_word = words[-1]

        # =============================================================
        # Monta o formato esperado por ORTHOGRAPHY_RULES:
        #
        #     palavra ^ sufixo
        # =============================================================

        candidate = (
            previous_word
            + ' ^ '
            + suffix
        )

        corrected = candidate

        # =============================================================
        # Executa as regras na ordem em que foram configuradas.
        # =============================================================

        for pattern, replacement in (
            _plover_system.ORTHOGRAPHY_RULES
        ):

            try:
                new_value = re.sub(
                    pattern,
                    replacement,
                    corrected,
                )
            except re.error:
                continue

            if new_value != corrected:
                corrected = new_value
                break

        else:
            # Nenhuma regra foi aplicada.
            return suffix_mapping

        # =============================================================
        # O replacement da regra normalmente produz a palavra final.
        #
        # Exemplo:
        #
        #     apareço ^ e
        #
        #     ->
        #
        #     aparece
        # =============================================================

        corrected_word = corrected.strip()

        if not corrected_word:
            return suffix_mapping

        # =============================================================
        # Descobre o maior prefixo em comum entre:
        #
        #     apareço
        #
        # e:
        #
        #     aparece
        #
        # resultado:
        #
        #     "apare"
        #
        # Então:
        #
        #     apagar: ç
        #     inserir: ce
        # =============================================================

        common_length = 0

        max_common = min(
            len(previous_word),
            len(corrected_word),
        )

        while (
            common_length < max_common
            and previous_word[common_length]
            == corrected_word[common_length]
        ):
            common_length += 1

        chars_to_delete = (
            len(previous_word)
            - common_length
        )

        text_to_append = (
            corrected_word[common_length:]
        )

        # =============================================================
        # IMPORTANTE:
        #
        # A parte nova precisa continuar sendo ATTACH.
        #
        # Antes estávamos retornando:
        #
        #     {#BackSpace}ce
        #
        # "ce" era texto normal e por isso o Plover colocava espaço.
        #
        # Agora:
        #
        #     {#BackSpace}{^ce}
        #
        # o "ce" continua anexado à palavra.
        # =============================================================

        replacement = (
            '{#BackSpace}' * chars_to_delete
            + '{^'
            + text_to_append
            + '}'
        )

        return replacement

    def translate_stroke_with_skfl_suffix(
        self,
        stroke,
    ):

        # =============================================================
        # Só interfere no sistema Português.
        # =============================================================

        if _plover_system.NAME != 'Portuguese Stenotype':
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 1. PRIORIDADE ABSOLUTA:
        #
        # Entrada literal do stroke completo.
        # =============================================================

        direct_mapping = self.lookup(
            (stroke,)
        )

        if direct_mapping is not None:
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 2. Identifica SKFL.
        # =============================================================

        keys = set(
            stroke.steno_keys
        )

        skfl_keys = {
            'S-',
            'K-',
            'F-',
            'L-',
        }

        if not skfl_keys.issubset(keys):
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 3. Remove SKFL.
        # =============================================================

        remaining_keys = (
            keys - skfl_keys
        )

        if not remaining_keys:
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 4. Não permite S/K/F/L no stroke-base.
        # =============================================================

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

        if remaining_keys.intersection(
            forbidden_keys
        ):
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 5. Reconstrói o stroke-base.
        # =============================================================

        try:
            base_stroke = type(stroke)(
                remaining_keys
            )
        except (
            TypeError,
            ValueError,
        ):
            return original_translate_stroke(
                self,
                stroke,
            )

        # =============================================================
        # 6. Procura entrada direta.
        # =============================================================

        direct_base_mapping = self.lookup(
            (base_stroke,)
        )

        if direct_base_mapping is not None:

            suffix_mapping = _make_suffix(
                direct_base_mapping
            )

            if suffix_mapping is None:
                return original_translate_stroke(
                    self,
                    stroke,
                )

            # Aplica ORTHOGRAPHY_RULES.
            suffix_mapping = _apply_orthography(
                self,
                suffix_mapping,
            )

            translation = (
                _plover_translation.Translation(
                    [stroke],
                    suffix_mapping,
                )
            )

            self.translate_translation(
                translation
            )

            return

        # =============================================================
        # 7. Caso especial para strokes que usam '*'.
        #
        # Exemplo:
        #
        #     A*R -> ara
        # =============================================================

        if '*' in base_stroke.rtfcre:

            try:
                max_len = (
                    self._dictionary.longest_key
                )

                mapping = (
                    self._lookup_with_prefix(
                        max_len,
                        self._state.translations,
                        [base_stroke],
                    )
                )

                if mapping is None:

                    t = self._find_longest_match(
                        1,
                        max_len,
                        base_stroke,
                        _plover_system.SUFFIX_KEYS,
                    )

                    if t is not None:
                        mapping = t.english

            except (
                AttributeError,
                TypeError,
                KeyError,
                IndexError,
            ):
                mapping = None

            if mapping is not None:

                suffix_mapping = _make_suffix(
                    mapping
                )

                if suffix_mapping is not None:

                    # Aplica ORTHOGRAPHY_RULES.
                    suffix_mapping = (
                        _apply_orthography(
                            self,
                            suffix_mapping,
                        )
                    )

                    translation = (
                        _plover_translation.Translation(
                            [stroke],
                            suffix_mapping,
                        )
                    )

                    self.translate_translation(
                        translation
                    )

                    return

        # =============================================================
        # 8. Não conseguiu resolver SKFL.
        # =============================================================

        return original_translate_stroke(
            self,
            stroke,
        )

    translator_class.translate_stroke = (
        translate_stroke_with_skfl_suffix
    )

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
    # Ç + E -> C + E
    (
        r'^(.+)ç \^ e$',
        r'\1ce',
    ),

    # Ç + I -> C + I
    (
        r'^(.+)ç \^ i$',
        r'\1ci',
    ),

    # Collapse vowels in suffixes
    (
        r'^(.+)[aeouiáéíóúãõâêôàü] \^ ([aeouiáéíóúãõâêôàü]\w*)$',
        r'\1\2',
    ),
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
