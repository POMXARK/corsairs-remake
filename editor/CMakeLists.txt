# The editor windows of the game: a module the engine builds when it is configured with
#   -DSTORM_EXTRA_MODULES=<this directory>
# The windows register themselves when the module is linked and open in the editor (engine --editor).
STORM_SETUP(
        TARGET_NAME corsairs_editor
        TYPE storm_module
        DEPENDENCIES core editor
)
