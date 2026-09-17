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
        5. Converte o resultado em attach.

    Exemplos:

        E
            -> e

        SKFL E
            -> {^e}

        RAEUR
            -> {^rário}

        SKFLRAEUR
            -> {^rário}

        AR
            -> ar

        A*R
            -> ara

        SKFLA*R
            -> {^ara}
    """

    translator_class = _plover_translation.Translator

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
        Converte uma tradução em attach.

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

        # Já é attach.
        if mapping.startswith('{^'):
            return mapping

        # Texto normal + attach.
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

        # Texto normal.
        return (
            '{^'
            + mapping
            + '}'
        )

    def _resolve_base_with_asterisk(
        translator,
        base_stroke,
    ):
        """
        Resolve strokes que dependem do mecanismo normal de '*'.

        Exemplo:

            A*R -> ara
        """

        try:
            max_len = (
                translator._dictionary.longest_key
            )

            mapping = (
                translator._lookup_with_prefix(
                    max_len,
                    translator._state.translations,
                    [base_stroke],
                )
            )

            if mapping is None:
                t = translator._find_longest_match(
                    1,
                    max_len,
                    base_stroke,
                    tuple(
                        _plover_system.SUFFIX_KEYS
                    ),
                )

                if t is not None:
                    mapping = t.english

            return mapping

        except (
            AttributeError,
            TypeError,
            KeyError,
            IndexError,
        ):
            return None

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
        # Se o stroke completo existir no dicionário,
        # deixa o dicionário vencer.
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
        # 6. Entrada direta no dicionário.
        #
        # Exemplos:
        #
        #     E -> e
        #     AR -> ar
        #     RAEUR -> {^rário}
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
        # 7. Caso especial:
        #
        # O stroke-base contém '*'.
        #
        # Exemplos:
        #
        #     A*R -> ara
        #     SKFLA*R -> {^ara}
        # =============================================================

        if '*' in base_stroke.rtfcre:
            mapping = _resolve_base_with_asterisk(
                self,
                base_stroke,
            )

            if mapping is not None:
                suffix_mapping = _make_suffix(
                    mapping
                )

                if suffix_mapping is not None:
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


def _patch_orthography_rules():
    """
    Faz o attach do Plover aplicar ORTHOGRAPHY_RULES antes que
    a Action seja finalizada e registrada no contexto.

    A lógica é geral e não depende de SKFL.

    Exemplos:

        apareço + {^e}
            -> aparece

        apareço + {^i}
            -> apareci

    O patch altera somente o _meta_to_action do módulo
    plover.formatting, sem modificar os arquivos do Plover.
    """

    import plover.formatting as _plover_formatting

    # =============================================================
    # Remove o patch antigo que atuava em _translation_to_actions.
    #
    # Isso é importante porque versões anteriores desta função
    # instalavam um patch em uma camada posterior do formatter.
    # =============================================================

    old_translation_patch = getattr(
        _plover_formatting,
        '_portuguese_orthography_patch_state',
        None,
    )

    if old_translation_patch is not None:
        _plover_formatting._translation_to_actions = (
            old_translation_patch['original']
        )

        try:
            delattr(
                _plover_formatting,
                '_portuguese_orthography_patch_state',
            )
        except AttributeError:
            pass

    # =============================================================
    # Se este novo patch já estiver instalado, não empilha outro.
    # =============================================================

    old_meta_patch = getattr(
        _plover_formatting,
        '_portuguese_orthography_meta_patch_state',
        None,
    )

    if old_meta_patch is not None:
        _plover_formatting._meta_to_action = (
            old_meta_patch['original']
        )

    original_meta_to_action = (
        _plover_formatting._meta_to_action
    )

    # =============================================================
    # Obtém diretamente o meta `attach` original.
    #
    # O _meta_to_action do Plover faz exatamente:
    #
    #     meta_fn(ctx, meta_arg)
    #
    # Portanto podemos executar o attach normal e corrigir a
    # Action imediatamente, antes do _finalize_action().
    # =============================================================

    meta_name, _ = _plover_formatting._parse_meta(
        '^e'
    )

    # Não usamos o valor acima para a lógica; ele apenas garante
    # que _parse_meta continua disponível nesta versão do Plover.

    attach_plugin = (
        _plover_formatting.registry.get_plugin(
            'meta',
            'attach',
        )
    )

    original_attach = attach_plugin.obj

    # =============================================================
    # Aplica ORTHOGRAPHY_RULES.
    # =============================================================

    def _apply_rules(
        word,
        suffix,
    ):
        """
        Aplica ORTHOGRAPHY_RULES à combinação:

            palavra ^ sufixo

        Retorna a forma corrigida ou None.
        """

        if not isinstance(
            word,
            str,
        ) or not word:
            return None

        if not isinstance(
            suffix,
            str,
        ) or not suffix:
            return None

        # Algumas versões/fluxos podem fornecer o argumento
        # do attach incluindo o ^ inicial.
        if suffix.startswith('^'):
            suffix = suffix[1:]

        if not suffix:
            return None

        candidate = (
            word
            + ' ^ '
            + suffix
        )

        for pattern, replacement in (
            _plover_system.ORTHOGRAPHY_RULES
        ):
            try:
                corrected = re.sub(
                    pattern,
                    replacement,
                    candidate,
                )
            except re.error:
                continue

            if corrected != candidate:
                return corrected.strip()

        return None

    # =============================================================
    # Intercepta somente o meta `attach`.
    #
    # Todos os outros metas continuam exatamente como no Plover.
    # =============================================================

    def _meta_to_action_with_portuguese_orthography(
        meta,
        ctx,
    ):
        meta_name, meta_arg = (
            _plover_formatting._parse_meta(meta)
        )

        # ---------------------------------------------------------
        # Outros sistemas ou outros metas:
        # comportamento original.
        # ---------------------------------------------------------

        if (
            _plover_system.NAME
            != 'Portuguese Stenotype'
            or meta_name != 'attach'
        ):
            return original_meta_to_action(
                meta,
                ctx,
            )

        # ---------------------------------------------------------
        # Executa o attach ORIGINAL.
        #
        # Neste momento a Action ainda não foi finalizada e
        # ainda não foi passada para ctx.translated().
        # ---------------------------------------------------------

        action = original_attach(
            ctx,
            meta_arg,
        )

        # ---------------------------------------------------------
        # Descobre a última palavra antes deste attach.
        #
        # Como o _meta_to_action é chamado antes de
        # ctx.translated(action), ela ainda é a palavra anterior.
        # ---------------------------------------------------------

        previous_words = ctx.last_words(
            count=1,
            strip=True,
        )

        if not previous_words:
            return action

        current_word = previous_words[0]

        if not current_word:
            return action

        # ---------------------------------------------------------
        # Normaliza somente o ^ inicial do argumento.
        # ---------------------------------------------------------

        suffix = meta_arg

        if isinstance(
            suffix,
            str,
        ) and suffix.startswith('^'):
            suffix = suffix[1:]

        # ---------------------------------------------------------
        # Aplica as regras.
        # ---------------------------------------------------------

        corrected_word = _apply_rules(
            current_word,
            suffix,
        )

        # ---------------------------------------------------------
        # Nenhuma regra aplicável:
        # mantém exatamente a Action criada pelo Plover.
        # ---------------------------------------------------------

        if corrected_word is None:
            return action

        # ---------------------------------------------------------
        # A regra foi aplicada.
        #
        # Corrige a Action ANTES de _finalize_action().
        # ---------------------------------------------------------

        action.prev_replace = current_word
        action.prev_attach = True
        action.text = corrected_word
        action.word = corrected_word
        action.orthography = True

        return action

    # =============================================================
    # Instala o patch.
    # =============================================================

    _plover_formatting._meta_to_action = (
        _meta_to_action_with_portuguese_orthography
    )

    # =============================================================
    # Guarda o original para futuros reloads.
    # =============================================================

    _plover_formatting._portuguese_orthography_meta_patch_state = {
        'original': original_meta_to_action,
    }

_patch_orthography_rules()
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
    (
        r'^(.+)ço \^ e$',
        r'\1ce',
    ),
    (
        r'^(.+)ço \^ i$',
        r'\1ci',
    ),
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
