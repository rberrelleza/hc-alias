AJS.$("#select2-users").auiSelect2();

function toggleHidden(e) {
    $('.toggle').toggleClass('hidden');
}

$('a.cancel').on('click', toggleHidden);

$('.spy a.aui-inline-dialog-trigger, .alias-list a.aui-inline-dialog-trigger').on('click', function() {
    toggleHidden();
    $('input#alias-name').val('@').focus();
});

$('ul.aliases li').on('click', function(e) {
    toggleHidden();
    var alias = $(e.currentTarget).data().alias;
    var mentions = JSON.parse($(e.currentTarget).data().mentions.replace(/'/g, '"'));
    $('input#alias-name').val(alias);
    AJS.$("#select2-users").val(mentions).trigger('change');
});

(function () {

    $(document).ready(function () {
        var signedRequest = $("meta[name=acpt]").attr("content");
        $.ajaxSetup({
            beforeSend: function (request) {
                request.setRequestHeader("X-acpt", signedRequest);
            }
        });
    });

    $('form').on('submit', function (e) {
        e.stopPropagation();
        e.preventDefault();
        $.ajax({
            type: 'POST',
            url: '/create',
            data: JSON.stringify({
                alias: $('input#alias-name').val(),
                mentions: $('#select2-users').val(),
                room: $('input#room').val()
            }),
            success: function() {
                toggleHidden();
                window.location.reload();
            }
        });
    });

})();
